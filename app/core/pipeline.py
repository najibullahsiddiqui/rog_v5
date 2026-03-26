from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import List, Tuple

from app.core.category_utils import category_from_question
from app.core.config import MIN_CONTEXT_CHARS
from app.core.constants import REFUSAL_TEXT
from app.core.llm import generate_answer
from app.core.retrieval import Retriever


DIRECT_MATCH_THRESHOLD = 0.80
NEAR_MATCH_THRESHOLD = 0.66
MIN_GROUNDED_RERANK_SCORE = 0.15
MAX_SYNTHESIS_CITATIONS = 3


def format_page_label(hit: dict) -> str:
    start = hit.get("page_start") or hit.get("page_no")
    end = hit.get("page_end") or start

    if start == end:
        return f"Page {start}"
    return f"Pages {start}-{end}"


def normalize_question_text(text: str) -> str:
    text = (text or "").strip().lower()
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"[^\w\s]", "", text)
    return text.strip()


def question_similarity(user_question: str, chunk_question: str) -> float:
    uq = normalize_question_text(user_question)
    cq = normalize_question_text(chunk_question)

    if not uq or not cq:
        return 0.0

    return SequenceMatcher(None, uq, cq).ratio()


def extract_question_from_chunk(text: str) -> str:
    if not text:
        return ""

    cleaned = text.strip()

    patterns = [
        r"^\s*\d{1,3}[\.\)]\s*(.+?\?)",
        r"^\s*Q(?:uestion)?\s*[:\-]\s*(.+?\?)",
        r"^\s*(.+?\?)",
    ]

    for pattern in patterns:
        m = re.search(pattern, cleaned, flags=re.IGNORECASE | re.DOTALL)
        if m:
            return re.sub(r"\s+", " ", m.group(1)).strip()

    return ""


def clean_answer_prefix(text: str) -> str:
    if not text:
        return ""

    cleaned = text.strip()
    cleaned = re.sub(
        r"^\s*(?:a|ans|answer)\s*[:\-]\s*",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )

    lines = cleaned.splitlines()
    normalized_lines = [re.sub(r"[ \t]+", " ", line).rstrip() for line in lines]

    cleaned = "\n".join(normalized_lines)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()

    return cleaned


def extract_answer_from_chunk(text: str) -> str:
    if not text:
        return ""

    cleaned = text.strip()

    m = re.search(
        r"\b(?:Ans|Answer|A)\s*[:\-]\s*(.*)",
        cleaned,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if m:
        answer = m.group(1).strip()
    else:
        answer = re.sub(
            r"^\s*(?:\d{1,3}[\.\)]\s*)?.+?\?\s*",
            "",
            cleaned,
            count=1,
            flags=re.DOTALL,
        ).strip()

        if not answer:
            answer = cleaned

    next_q = re.search(r"\n\s*\d{1,3}[\.\)]\s+.+?\?", answer, flags=re.DOTALL)
    if next_q:
        answer = answer[:next_q.start()].strip()

    answer = answer.replace("\r\n", "\n").replace("\r", "\n")
    answer = re.sub(r"\n•\n", "\n• ", answer)
    answer = re.sub(r"\n{3,}", "\n\n", answer)

    return clean_answer_prefix(answer)


def build_citation(hit: dict) -> dict:
    return {
        "doc_name": hit["doc_name"],
        "page_no": hit.get("page_no"),
        "page_start": hit.get("page_start"),
        "page_end": hit.get("page_end"),
        "page_label": format_page_label(hit),
        "heading": hit.get("heading"),
        "excerpt": hit["text"][:600],
        "score": round(float(hit.get("rerank_score", 0.0)), 4),
        "source_metadata": {
            "retrieval_channel": hit.get("retrieval_channel"),
            "vector_score": hit.get("vector_score"),
            "bm25_score": hit.get("bm25_score"),
            "hybrid_score": hit.get("hybrid_score"),
        },
    }


def compact_citations(hits: list[dict], limit: int = MAX_SYNTHESIS_CITATIONS) -> list[dict]:
    citations: list[dict] = []
    seen: set[tuple] = set()

    for hit in hits:
        key = (hit.get("doc_name"), hit.get("page_no"), (hit.get("heading") or "").strip().lower())
        if key in seen:
            continue
        seen.add(key)
        citations.append(build_citation(hit))
        if len(citations) >= limit:
            break

    return citations


def get_best_direct_match(question: str, hits: List[dict]) -> Tuple[dict | None, float, str, str]:
    best_hit = None
    best_score = 0.0
    best_chunk_question = ""
    best_chunk_answer = ""

    for hit in hits:
        chunk_text = hit.get("text", "")
        chunk_question = extract_question_from_chunk(chunk_text)
        if not chunk_question:
            continue

        score = question_similarity(question, chunk_question)
        if score > best_score:
            answer = extract_answer_from_chunk(chunk_text)
            if answer:
                best_hit = hit
                best_score = score
                best_chunk_question = chunk_question
                best_chunk_answer = answer

    return best_hit, best_score, best_chunk_question, best_chunk_answer


class QAPipeline:
    def __init__(self):
        self.retriever = Retriever()

    def ask(self, question: str) -> dict:
        normalized_question = normalize_question_text(question)
        category_hint = category_from_question(question)
        hits, retrieval_trace = self.retriever.retrieve_with_trace(question, category_hint=category_hint)

        grounded_hits: List[dict] = [h for h in hits if len((h.get("text") or "").strip()) > 60]
        if not grounded_hits:
            grounded_hits = hits[:5]

        if not grounded_hits:
            return {
                "answer": REFUSAL_TEXT,
                "grounded": False,
                "citations": [],
                "evidence_sources": [],
                "answer_source": "unresolved",
                "confidence": 0.0,
                "debug": {
                    "retrieved": len(hits),
                    "grounded": 0,
                    "top_rerank_score": None,
                    "flow": "refusal_no_hits",
                    "top_hits_preview": [],
                    "retrieval_trace": retrieval_trace,
                    "query_info": {
                        "normalized_question": normalized_question,
                        "category_hint": category_hint,
                    },
                },
            }

        top_hits = grounded_hits[:5]
        top_rerank_hit = grounded_hits[0]

        direct_hit, direct_match_score, direct_chunk_question, direct_chunk_answer = get_best_direct_match(
            question,
            grounded_hits,
        )

        context_parts: List[str] = []
        compact_for_context = compact_citations(top_hits, limit=4)
        for citation in compact_for_context:
            doc = citation.get("doc_name")
            page_label = citation.get("page_label")
            heading = citation.get("heading") or "N/A"
            excerpt = citation.get("excerpt") or ""
            context_parts.append(
                "\n".join(
                    [
                        f"Document: {doc}",
                        f"Page: {page_label}",
                        f"Heading: {heading}",
                        "Content:",
                        excerpt,
                    ]
                )
            )

        context = "\n\n---\n\n".join(context_parts).strip()

        if len(context) < MIN_CONTEXT_CHARS:
            fallback_hits = hits[:4]
            fallback_parts: List[str] = []
            for hit in fallback_hits:
                if not (hit.get("text") or "").strip():
                    continue
                fallback_parts.append(
                    "\n".join(
                        [
                            f"Document: {hit['doc_name']}",
                            f"Page: {format_page_label(hit)}",
                            f"Heading: {hit.get('heading') or 'N/A'}",
                            "Content:",
                            hit["text"][:700],
                        ]
                    )
                )
            fallback_context = "\n\n---\n\n".join(fallback_parts).strip()
            if fallback_context:
                context = fallback_context
                top_hits = fallback_hits

        if direct_hit and direct_chunk_answer and direct_match_score >= DIRECT_MATCH_THRESHOLD:
            answer = direct_chunk_answer
            flow = "faq_exact"
            answer_source = "faq_exact"
            citations = [build_citation(direct_hit)]

        elif direct_hit and direct_chunk_answer and direct_match_score >= NEAR_MATCH_THRESHOLD:
            answer = direct_chunk_answer
            flow = "faq_near"
            answer_source = "faq_near"
            citations = [build_citation(direct_hit)]

        else:
            top_score = float(top_rerank_hit.get("rerank_score") or 0.0)
            if top_score < MIN_GROUNDED_RERANK_SCORE:
                answer = REFUSAL_TEXT
                flow = "refusal_low_evidence"
                answer_source = "unresolved"
                citations = []
            else:
                answer = generate_answer(question, context).strip()
                answer = clean_answer_prefix(answer)
                flow = "pdf_synthesized"
                answer_source = "pdf_synthesized"
                citations = compact_citations(top_hits, limit=MAX_SYNTHESIS_CITATIONS)

        if not answer:
            answer = REFUSAL_TEXT

        lowered_answer = answer.lower().strip()
        grounded = lowered_answer != REFUSAL_TEXT.lower()

        if not grounded:
            citations = []
            answer_source = "unresolved"

        evidence_sources = sorted({c.get("doc_name") for c in citations if c.get("doc_name")})

        top_hits_preview = []
        for hit in hits[:5]:
            top_hits_preview.append(
                {
                    "doc_name": hit.get("doc_name"),
                    "page_label": format_page_label(hit),
                    "heading": hit.get("heading"),
                    "retrieval_channel": hit.get("retrieval_channel"),
                    "rerank_score": hit.get("rerank_score"),
                    "text_preview": (hit.get("text") or "")[:180],
                }
            )

        confidence = 0.0
        if grounded:
            if answer_source == "faq_exact":
                confidence = 1.0
            elif answer_source == "faq_near":
                confidence = round(float(direct_match_score), 4)
            else:
                confidence = round(float(top_rerank_hit.get("rerank_score") or 0.0), 4)

        return {
            "answer": answer,
            "grounded": grounded,
            "citations": citations,
            "evidence_sources": evidence_sources,
            "answer_source": answer_source,
            "confidence": confidence,
            "debug": {
                "retrieved": len(hits),
                "grounded": len(grounded_hits),
                "top_rerank_score": top_rerank_hit.get("rerank_score"),
                "direct_match_score": round(float(direct_match_score), 4),
                "direct_chunk_question": direct_chunk_question,
                "flow": flow,
                "top_hits_preview": top_hits_preview,
                "retrieval_trace": retrieval_trace,
                "query_info": {
                    "normalized_question": normalized_question,
                    "category_hint": category_hint,
                },
            },
        }

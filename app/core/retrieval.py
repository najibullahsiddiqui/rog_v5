from __future__ import annotations

import json
import pickle
import re
from difflib import SequenceMatcher
from typing import List

import faiss
import numpy as np
from sentence_transformers import SentenceTransformer, CrossEncoder

from app.core.config import (
    INDEX_DIR,
    EMBEDDING_MODEL,
    RERANKER_MODEL,
    TOP_K_VECTOR,
    TOP_K_BM25,
    TOP_K_RERANK,
)


DIRECT_MATCH_THRESHOLD = 0.80


def normalize_question_text(text: str) -> str:
    text = (text or "").strip().lower()
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"[^\w\s]", "", text)
    return text.strip()


def normalize_token(token: str) -> str:
    token = token.lower().strip()

    # very light normalization
    if token.endswith("ing") and len(token) > 5:
        token = token[:-3]
    elif token.endswith("ed") and len(token) > 4:
        token = token[:-2]
    elif token.endswith("es") and len(token) > 4:
        token = token[:-2]
    elif token.endswith("s") and len(token) > 3:
        token = token[:-1]

    return token


def preprocess_for_bm25(text: str) -> List[str]:
    text = normalize_question_text(text)
    tokens = [normalize_token(t) for t in text.split() if t]

    stopwords = {
        "the", "is", "are", "a", "an", "of", "to", "in", "for", "on",
        "by", "with", "does", "do", "did", "can", "i", "we", "you",
        "it", "this", "that", "be"
    }

    return [t for t in tokens if t and t not in stopwords]


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


def question_similarity(user_question: str, chunk_question: str) -> float:
    uq = normalize_question_text(user_question)
    cq = normalize_question_text(chunk_question)

    if not uq or not cq:
        return 0.0

    base = SequenceMatcher(None, uq, cq).ratio()

    # containment boost
    if uq in cq or cq in uq:
        base = max(base, 0.92)

    uq_tokens = set(preprocess_for_bm25(uq))
    cq_tokens = set(preprocess_for_bm25(cq))
    if uq_tokens and cq_tokens:
        overlap = len(uq_tokens & cq_tokens) / max(1, len(uq_tokens | cq_tokens))
        base = max(base, overlap * 0.95)

    return min(base, 1.0)


def expand_query(query: str) -> List[str]:
    q = normalize_question_text(query)
    expansions = [q]

    # lightweight domain expansions
    if "copyright" in q and "fact" in q:
        expansions.extend([
            "copyright factual information",
            "copyright protects expression not facts",
            "copyright ideas concepts factual information",
        ])

    if "idea" in q and "copyright" in q:
        expansions.extend([
            "copyright protects expression not ideas",
            "ideas concepts not protected by copyright",
        ])

    # dedupe preserving order
    seen = set()
    final = []
    for item in expansions:
        if item and item not in seen:
            seen.add(item)
            final.append(item)

    return final


class Retriever:
    def __init__(self):
        self.index_path = INDEX_DIR / "faiss.index"
        self.chunks_path = INDEX_DIR / "chunks.jsonl"
        self.bm25_path = INDEX_DIR / "bm25.pkl"
        self._load()

    def _load(self):
        if not self.index_path.exists() or not self.chunks_path.exists() or not self.bm25_path.exists():
            raise FileNotFoundError("Index files not found. Run ingestion first.")

        self.index = faiss.read_index(str(self.index_path))
        self.embedder = SentenceTransformer(EMBEDDING_MODEL)
        self.reranker = CrossEncoder(RERANKER_MODEL)

        with open(self.chunks_path, "r", encoding="utf-8") as f:
            self.chunks = [json.loads(line) for line in f if line.strip()]

        with open(self.bm25_path, "rb") as f:
            self.bm25 = pickle.load(f)

        self.chunk_questions = []
        for idx, chunk in enumerate(self.chunks):
            q = extract_question_from_chunk(chunk.get("text", ""))
            self.chunk_questions.append((idx, q))

    def _direct_match_hits(self, query: str) -> List[dict]:
        best_idx = None
        best_score = 0.0

        for idx, chunk_question in self.chunk_questions:
            if not chunk_question:
                continue

            score = question_similarity(query, chunk_question)
            if score > best_score:
                best_idx = idx
                best_score = score

        if best_idx is not None and best_score >= DIRECT_MATCH_THRESHOLD:
            hit = dict(self.chunks[best_idx])
            hit["rerank_score"] = 1.0
            hit["direct_match_score"] = float(best_score)
            return [hit]

        return []

    def _vector_hits_for_query(self, query: str) -> List[dict]:
        q_emb = self.embedder.encode([query], normalize_embeddings=True)
        q_emb = np.array(q_emb, dtype="float32")

        scores, indices = self.index.search(q_emb, TOP_K_VECTOR)
        vector_hits = []

        for idx, score in zip(indices[0], scores[0]):
            if idx < 0:
                continue
            hit = dict(self.chunks[idx])
            hit["vector_score"] = float(score)
            vector_hits.append(hit)

        return vector_hits

    def _bm25_hits_for_query(self, query: str) -> List[dict]:
        bm25_scores = self.bm25.get_scores(preprocess_for_bm25(query))
        bm25_top_idx = np.argsort(bm25_scores)[::-1][:TOP_K_BM25]

        bm25_hits = []
        for idx in bm25_top_idx:
            hit = dict(self.chunks[int(idx)])
            hit["bm25_score"] = float(bm25_scores[int(idx)])
            bm25_hits.append(hit)

        return bm25_hits

    def retrieve(self, query: str) -> List[dict]:
        # FAST PATH
        direct_hits = self._direct_match_hits(query)
        if direct_hits:
            return direct_hits

        expanded_queries = expand_query(query)

        merged = {}

        for q in expanded_queries:
            vector_hits = self._vector_hits_for_query(q)
            bm25_hits = self._bm25_hits_for_query(q)

            for hit in vector_hits + bm25_hits:
                key = hit["chunk_id"]
                if key not in merged:
                    merged[key] = hit
                else:
                    merged[key].update(hit)

        candidates = list(merged.values())
        if not candidates:
            return []

        for c in candidates:
            c["hybrid_score"] = (
                float(c.get("vector_score", 0.0))
                + float(c.get("bm25_score", 0.0) / 10.0)
            )

        rerank_pairs = [[query, c["text"]] for c in candidates]
        rerank_scores = self.reranker.predict(rerank_pairs)

        for c, rr in zip(candidates, rerank_scores):
            score = float(rr)

            # slight FAQ boost
            text = (c.get("text") or "").strip()
            if "?" in text[:200]:
                score += 0.08

            c["rerank_score"] = score

        candidates.sort(key=lambda x: x["rerank_score"], reverse=True)
        return candidates[:TOP_K_RERANK]
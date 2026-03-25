from __future__ import annotations

import json
import pickle
import re
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List, Dict, Optional, Tuple

import faiss
import fitz
import numpy as np
from rank_bm25 import BM25Okapi
from sentence_transformers import SentenceTransformer

from app.core.config import PDF_DIR, INDEX_DIR, EMBEDDING_MODEL


SKIP_DOC_NAMES = {
    "Question_Answer_Document_2.pdf",
}

DUPLICATE_PREFERRED = {
    "Chatboat-FAQ-(1).pdf": False,
    "FAQ-SICLD.pdf": True,
}


@dataclass
class Chunk:
    chunk_id: str
    doc_name: str
    doc_path: str
    page_start: int
    page_end: int
    page_no: int
    heading: Optional[str]
    question_no: Optional[str]
    section_heading: Optional[str]
    text: str


# -----------------------------
# Generic helpers
# -----------------------------

def slugify(text: str, max_len: int = 80) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = text.strip("-")
    return text[:max_len] or "untitled"


def preprocess_for_bm25(text: str) -> List[str]:
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return [t for t in text.split() if t]


def clean_text(text: str) -> str:
    if not text:
        return ""

    text = text.replace("\u00ad", "")
    text = text.replace("\uf0b7", "•")
    text = text.replace("\u2022", "•")
    text = text.replace("\u2013", "-").replace("\u2014", "-")
    text = text.replace("\u2018", "'").replace("\u2019", "'")
    text = text.replace("\u201c", '"').replace("\u201d", '"')
    text = text.replace("\xa0", " ")

    lines = [ln.rstrip() for ln in text.splitlines()]
    cleaned_lines: List[str] = []

    for ln in lines:
        stripped = ln.strip()

        if not stripped:
            cleaned_lines.append("")
            continue

        # obvious page noise
        if re.fullmatch(r"\d+", stripped):
            continue
        if re.fullmatch(r"\d+\s*/\s*\d+", stripped):
            continue
        if re.fullmatch(r"Page\s+\d+", stripped, re.IGNORECASE):
            continue
        if re.fullmatch(r"Page\s+\d+\s+of\s+\d+", stripped, re.IGNORECASE):
            continue
        if re.fullmatch(r"-?\s*\d+\s*-?", stripped):
            continue

        cleaned_lines.append(stripped)

    text = "\n".join(cleaned_lines)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text


def normalize_inline_spaces(text: str) -> str:
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\s+\n", "\n", text)
    return text.strip()


def normalize_question_text(text: str) -> str:
    text = normalize_inline_spaces(text)
    text = re.sub(r"^(?:Q(?:uestion)?\s*)?(?:No\.?\s*)?\d+\s*[.)-]?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def normalize_answer_text(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^(?:Ans(?:wer)?\.?|A)\s*[:\-]\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract_pages(pdf_path: Path) -> List[Dict]:
    doc = fitz.open(pdf_path)
    pages: List[Dict] = []

    for page_num in range(doc.page_count):
        page = doc[page_num]
        text = page.get_text("text")
        pages.append(
            {
                "page_no": page_num + 1,
                "text": clean_text(text),
            }
        )

    doc.close()
    return pages


def flatten_page_lines(pages: List[Dict]) -> List[Dict]:
    all_lines: List[Dict] = []

    for page in pages:
        page_no = page["page_no"]
        for raw_line in page["text"].split("\n"):
            text = raw_line.strip()
            if not text:
                continue
            all_lines.append(
                {
                    "text": text,
                    "page_no": page_no,
                }
            )

    return all_lines


# -----------------------------
# Heuristics
# -----------------------------

QUESTION_WORD_RE = re.compile(
    r"\b("
    r"what|how|whether|when|where|who|whom|whose|which|why|can|could|"
    r"is|are|was|were|do|does|did|shall|should|may|might|will|would"
    r")\b",
    re.IGNORECASE,
)

QUESTION_START_RE = re.compile(
    r"^(?:Q(?:uestion)?\s*)?(?P<num>\d{1,3})\s*[.)-]\s*(?P<body>.+)$",
    re.IGNORECASE,
)

ANSWER_START_RE = re.compile(
    r"^(?:Ans(?:wer)?\.?|A)\s*[:\-]\s*(.*)$",
    re.IGNORECASE,
)

INLINE_ANSWER_SPLIT_RE = re.compile(
    r"^(?P<q>.*?\?)\s*(?:Ans(?:wer)?\.?|A)\s*[:\-]\s*(?P<a>.+)$",
    re.IGNORECASE,
)

ORPHAN_NUMBER_RE = re.compile(r"^\d{1,3}[.)]?$")
URL_ONLY_RE = re.compile(r"^(?:https?://|www\.)\S+$", re.IGNORECASE)
EMAIL_ONLY_RE = re.compile(r"^[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}$", re.IGNORECASE)


def is_noise_line(text: str) -> bool:
    t = text.strip()

    if not t:
        return True

    if ORPHAN_NUMBER_RE.fullmatch(t):
        return True

    if URL_ONLY_RE.fullmatch(t):
        return True

    if EMAIL_ONLY_RE.fullmatch(t):
        return True

    # common PDF/footer/header junk
    if re.fullmatch(r"trade marks registry", t, re.IGNORECASE):
        return True
    if re.fullmatch(r"copyright office", t, re.IGNORECASE):
        return True
    if re.fullmatch(r"intellectual property india", t, re.IGNORECASE):
        return True
    if re.fullmatch(r"frequently asked questions", t, re.IGNORECASE):
        return False  # keep; may be useful context
    if re.fullmatch(r"faq[s]?", t, re.IGNORECASE):
        return False

    return False


def is_section_heading(text: str) -> bool:
    t = text.strip()

    if not t:
        return False
    if len(t) > 120:
        return False
    if t.endswith("?"):
        return False
    if ANSWER_START_RE.match(t):
        return False
    if QUESTION_START_RE.match(t):
        return False

    # all caps or title-ish short labels
    words = t.split()
    if len(words) <= 8:
        if re.fullmatch(r"[A-Z0-9&/(),.\- ]{3,}", t):
            return True

        title_like = sum(1 for w in words if w[:1].isupper()) >= max(1, len(words) - 1)
        if title_like and len(t) <= 70 and ":" not in t:
            lower_blocklist = {
                "government of india",
                "office of the controller general",
                "department for promotion",
            }
            if t.lower() not in lower_blocklist:
                return True

    return False


def parse_question_start(text: str) -> Tuple[Optional[str], Optional[str]]:
    m = QUESTION_START_RE.match(text)
    if not m:
        return None, None

    q_no = m.group("num")
    q_body = m.group("body").strip()
    return q_no, q_body


def is_probable_question_line(text: str) -> bool:
    t = text.strip()

    if not t:
        return False
    if ANSWER_START_RE.match(t):
        return False
    if is_section_heading(t):
        return False

    q_no, q_body = parse_question_start(t)
    if q_no and q_body:
        return True

    if t.endswith("?"):
        return True

    if QUESTION_WORD_RE.search(t) and len(t) <= 220:
        return True

    return False


def has_question_semantics(text: str) -> bool:
    t = text.strip()
    return t.endswith("?") or bool(QUESTION_WORD_RE.search(t))


def looks_like_question_continuation(text: str) -> bool:
    t = text.strip()

    if not t:
        return False
    if ANSWER_START_RE.match(t):
        return False
    if is_section_heading(t):
        return False
    if parse_question_start(t)[0] is not None:
        return False
    if ORPHAN_NUMBER_RE.fullmatch(t):
        return False

    return len(t) <= 220


def looks_like_new_question(text: str) -> bool:
    t = text.strip()

    if not t:
        return False

    q_no, _ = parse_question_start(t)
    if q_no is not None:
        return True

    return False


def split_inline_answer(text: str) -> Tuple[Optional[str], Optional[str]]:
    m = INLINE_ANSWER_SPLIT_RE.match(text.strip())
    if not m:
        return None, None
    return m.group("q").strip(), m.group("a").strip()


def join_question_lines(lines: List[str]) -> str:
    text = " ".join(ln.strip() for ln in lines if ln.strip())
    text = re.sub(r"\s+", " ", text).strip()
    return normalize_question_text(text)


def join_answer_lines(lines: List[str]) -> str:
    parts: List[str] = []
    bullet_buffer: List[str] = []

    for ln in lines:
        line = ln.strip()
        if not line:
            continue

        if re.match(r"^[•\-]\s+", line):
            if bullet_buffer:
                parts.append("\n".join(bullet_buffer))
                bullet_buffer = []
            bullet_buffer.append(line)
        else:
            if bullet_buffer:
                bullet_buffer.append(line)
            else:
                parts.append(line)

    if bullet_buffer:
        parts.append("\n".join(bullet_buffer))

    text = "\n".join(parts)
    text = normalize_answer_text(text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# -----------------------------
# FAQ parser v3 (state machine)
# -----------------------------

def extract_qa_state_machine(pages: List[Dict]) -> List[Dict]:
    lines = flatten_page_lines(pages)

    qa_pairs: List[Dict] = []

    state = "SEEK_QUESTION"
    current_section: Optional[str] = None

    current_q_no: Optional[str] = None
    current_q_lines: List[str] = []
    current_a_lines: List[str] = []
    current_page_start: Optional[int] = None
    current_page_end: Optional[int] = None

    def reset_current():
        nonlocal current_q_no, current_q_lines, current_a_lines, current_page_start, current_page_end
        current_q_no = None
        current_q_lines = []
        current_a_lines = []
        current_page_start = None
        current_page_end = None

    def start_question(text: str, page_no: int):
        nonlocal current_q_no, current_q_lines, current_page_start, current_page_end

        q_no, q_body = parse_question_start(text)
        current_q_no = q_no

        if q_body is not None:
            current_q_lines = [q_body]
        else:
            current_q_lines = [text.strip()]

        current_page_start = page_no
        current_page_end = page_no

    def append_q(text: str, page_no: int):
        nonlocal current_page_end
        current_q_lines.append(text.strip())
        current_page_end = page_no

    def start_answer(text: str, page_no: int):
        nonlocal current_page_end, current_a_lines
        clean = re.sub(r"^(?:Ans(?:wer)?\.?|A)\s*[:\-]\s*", "", text.strip(), flags=re.IGNORECASE)
        if clean:
            current_a_lines.append(clean)
        current_page_end = page_no

    def append_a(text: str, page_no: int):
        nonlocal current_page_end
        current_a_lines.append(text.strip())
        current_page_end = page_no

    def finalize_current():
        if not current_q_lines:
            reset_current()
            return

        question = join_question_lines(current_q_lines)
        answer = join_answer_lines(current_a_lines)

        if not question:
            reset_current()
            return

        # strict: only keep items that really look like Q/A
        if not has_question_semantics(question) and current_q_no is None:
            reset_current()
            return

        if not answer or len(answer) < 3:
            reset_current()
            return

        qa_pairs.append(
            {
                "question_no": current_q_no,
                "question": question,
                "answer": answer,
                "section_heading": current_section,
                "page_start": current_page_start or 1,
                "page_end": current_page_end or current_page_start or 1,
            }
        )
        reset_current()

    i = 0
    while i < len(lines):
        row = lines[i]
        text = row["text"].strip()
        page_no = row["page_no"]

        if is_noise_line(text):
            i += 1
            continue

        if is_section_heading(text):
            current_section = text.strip()
            i += 1
            continue

        inline_q, inline_a = split_inline_answer(text)

        if state == "SEEK_QUESTION":
            if inline_q:
                reset_current()
                start_question(inline_q, page_no)
                append_a(inline_a, page_no)
                state = "CAPTURE_ANSWER"
                i += 1
                continue

            if is_probable_question_line(text):
                reset_current()
                start_question(text, page_no)
                state = "CAPTURE_QUESTION"
                i += 1
                continue

            i += 1
            continue

        if state == "CAPTURE_QUESTION":
            if inline_q:
                # current question had no answer -> discard and start fresh
                reset_current()
                start_question(inline_q, page_no)
                append_a(inline_a, page_no)
                state = "CAPTURE_ANSWER"
                i += 1
                continue

            if ANSWER_START_RE.match(text):
                start_answer(text, page_no)
                state = "CAPTURE_ANSWER"
                i += 1
                continue

            if looks_like_new_question(text):
                # previous question incomplete; replace with stronger candidate
                reset_current()
                start_question(text, page_no)
                state = "CAPTURE_QUESTION"
                i += 1
                continue

            if looks_like_question_continuation(text):
                append_q(text, page_no)
                i += 1
                continue

            # fallback: if line after question does not say Ans:, treat as answer start
            append_a(text, page_no)
            state = "CAPTURE_ANSWER"
            i += 1
            continue

        if state == "CAPTURE_ANSWER":
            if inline_q:
                finalize_current()
                start_question(inline_q, page_no)
                append_a(inline_a, page_no)
                state = "CAPTURE_ANSWER"
                i += 1
                continue

            if looks_like_new_question(text):
                finalize_current()
                start_question(text, page_no)
                state = "CAPTURE_QUESTION"
                i += 1
                continue

            if is_section_heading(text):
                # section after answer usually means answer ended
                finalize_current()
                current_section = text.strip()
                state = "SEEK_QUESTION"
                i += 1
                continue

            append_a(text, page_no)
            i += 1
            continue

    if state in {"CAPTURE_QUESTION", "CAPTURE_ANSWER"}:
        finalize_current()

    return qa_pairs


# -----------------------------
# Fallback chunker for non-FAQ docs
# -----------------------------

def chunk_text_by_paragraphs(pages: List[Dict], max_chars: int = 1400, min_chars: int = 300) -> List[Dict]:
    units: List[Dict] = []

    for page in pages:
        page_no = page["page_no"]
        paras = [p.strip() for p in re.split(r"\n\s*\n", page["text"]) if p.strip()]

        for para in paras:
            if is_noise_line(para):
                continue
            units.append(
                {
                    "text": para,
                    "page_no": page_no,
                }
            )

    chunks: List[Dict] = []
    buf: List[str] = []
    page_start: Optional[int] = None
    page_end: Optional[int] = None

    def flush():
        nonlocal buf, page_start, page_end
        text = "\n\n".join(buf).strip()
        if text:
            chunks.append(
                {
                    "heading": None,
                    "question_no": None,
                    "section_heading": None,
                    "text": text,
                    "page_start": page_start or 1,
                    "page_end": page_end or page_start or 1,
                }
            )
        buf = []
        page_start = None
        page_end = None

    for unit in units:
        txt = unit["text"]
        pno = unit["page_no"]

        if page_start is None:
            page_start = pno
        page_end = pno

        proposed = ("\n\n".join(buf + [txt])).strip()
        if len(proposed) > max_chars and len("\n\n".join(buf).strip()) >= min_chars:
            flush()
            page_start = pno
            page_end = pno
            buf = [txt]
        else:
            buf.append(txt)

    flush()
    return chunks


# -----------------------------
# Main extraction per PDF
# -----------------------------

FAQ_FILENAME_HINTS = {
    "faq",
    "copyright",
    "trademark",
    "trade-marks",
    "trade marks",
    "patent",
    "design",
    "gi",
    "sicld",
}


def is_faq_like_pdf(pdf_path: Path, pages: List[Dict]) -> bool:
    name = pdf_path.name.lower()
    joined_preview = "\n".join(page["text"][:1500] for page in pages[:3]).lower()

    if any(hint in name for hint in FAQ_FILENAME_HINTS):
        return True

    if "frequently asked questions" in joined_preview:
        return True
    if re.search(r"\bans(?:wer)?\s*[:\-]", joined_preview, re.IGNORECASE):
        return True
    if re.search(r"\b\d{1,3}\s*[.)-]\s+.+", joined_preview):
        return True

    return False


def make_chunk_id(pdf_path: Path, question_no: Optional[str], heading: Optional[str], idx: int) -> str:
    if question_no:
        return f"{pdf_path.stem}-Q{question_no}"
    if heading:
        return f"{pdf_path.stem}-{slugify(heading)}-{idx}"
    return f"{pdf_path.stem}-chunk-{idx}"


def extract_faq_from_pdf(pdf_path: Path) -> List[Chunk]:
    pages = extract_pages(pdf_path)

    if is_faq_like_pdf(pdf_path, pages):
        qa_pairs = extract_qa_state_machine(pages)
    else:
        qa_pairs = []

    chunks: List[Chunk] = []

    if qa_pairs:
        for idx, qa in enumerate(qa_pairs, start=1):
            q_no = qa.get("question_no")
            question = qa.get("question", "").strip()
            answer = qa.get("answer", "").strip()

            if q_no:
                chunk_text = f"Q{q_no}. {question}\n\nA: {answer}"
            else:
                chunk_text = f"Q. {question}\n\nA: {answer}"

            page_start = int(qa.get("page_start") or 1)
            page_end = int(qa.get("page_end") or page_start)

            chunk = Chunk(
                chunk_id=make_chunk_id(pdf_path, q_no, question, idx),
                doc_name=pdf_path.name,
                doc_path=str(pdf_path),
                page_start=page_start,
                page_end=page_end,
                page_no=page_start,
                heading=question,
                question_no=q_no,
                section_heading=qa.get("section_heading"),
                text=chunk_text,
            )
            chunks.append(chunk)

        return chunks

    # fallback for non-FAQ or low-confidence extraction
    paragraph_chunks = chunk_text_by_paragraphs(pages)

    for idx, item in enumerate(paragraph_chunks, start=1):
        text = item["text"].strip()
        if not text:
            continue

        heading = None
        first_line = text.splitlines()[0].strip()
        if len(first_line) <= 120:
            heading = first_line

        chunk = Chunk(
            chunk_id=make_chunk_id(pdf_path, None, heading, idx),
            doc_name=pdf_path.name,
            doc_path=str(pdf_path),
            page_start=item["page_start"],
            page_end=item["page_end"],
            page_no=item["page_start"],
            heading=heading,
            question_no=None,
            section_heading=item.get("section_heading"),
            text=text,
        )
        chunks.append(chunk)

    return chunks


# -----------------------------
# Indexing
# -----------------------------

def should_index(pdf_path: Path) -> bool:
    if pdf_path.name in SKIP_DOC_NAMES:
        return False
    if pdf_path.name in DUPLICATE_PREFERRED and not DUPLICATE_PREFERRED[pdf_path.name]:
        return False
    return True


def build_index(chunks: List[Chunk], embedder: SentenceTransformer):
    texts = [c.text for c in chunks]
    embeddings = embedder.encode(texts, normalize_embeddings=True, show_progress_bar=True)
    embeddings = np.asarray(embeddings, dtype="float32")

    dim = embeddings.shape[1]
    index = faiss.IndexFlatIP(dim)
    index.add(embeddings)

    tokenized = [preprocess_for_bm25(c.text) for c in chunks]
    bm25 = BM25Okapi(tokenized)

    return index, bm25


def save_outputs(chunks: List[Chunk], index, bm25):
    INDEX_DIR.mkdir(parents=True, exist_ok=True)
    faiss.write_index(index, str(INDEX_DIR / "faiss.index"))

    with open(INDEX_DIR / "chunks.jsonl", "w", encoding="utf-8") as f:
        for chunk in chunks:
            f.write(json.dumps(asdict(chunk), ensure_ascii=False) + "\n")

    with open(INDEX_DIR / "bm25.pkl", "wb") as f:
        pickle.dump(bm25, f)


# -----------------------------
# Runner
# -----------------------------

def run_ingestion(source_dir: Optional[Path] = None):
    source_dir = Path(source_dir or PDF_DIR)

    pdf_files = sorted(source_dir.glob("*.pdf"))
    pdf_files = [p for p in pdf_files if should_index(p)]

    if not pdf_files:
        raise FileNotFoundError(f"No PDFs found in {source_dir}")

    all_chunks: List[Chunk] = []

    print(f"[INFO] Source directory: {source_dir.resolve()}")
    print(f"[INFO] PDFs selected: {len(pdf_files)}")

    for pdf_path in pdf_files:
        doc_chunks = extract_faq_from_pdf(pdf_path)
        all_chunks.extend(doc_chunks)
        print(f"[OK] {pdf_path.name}: {len(doc_chunks)} chunks")

    print("\n[VERIFICATION] Sample chunks:")
    for i, chunk in enumerate(all_chunks[:10]):
        heading = (chunk.heading or chunk.text[:80]).replace("\n", " ")
        print(
            f"  {i + 1}. "
            f"pages={chunk.page_start}-{chunk.page_end} "
            f"qno={chunk.question_no or '-'} "
            f"{heading[:90]}..."
        )

    print(f"\n[INFO] Total chunks: {len(all_chunks)}")

    embedder = SentenceTransformer(EMBEDDING_MODEL)
    index, bm25 = build_index(all_chunks, embedder)
    save_outputs(all_chunks, index, bm25)

    print("[DONE] Re-index completed successfully.")
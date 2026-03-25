from __future__ import annotations

import json
import re
from pathlib import Path

import fitz


PROJECT_ROOT = Path(__file__).resolve().parents[1]

INPUT_JSONL = PROJECT_ROOT / "data" / "index" / "chunks.jsonl"
OUTPUT_JSONL = PROJECT_ROOT / "data" / "index" / "chunks_repaired.jsonl"
PDF_DIR = PROJECT_ROOT / "data" / "source_pdfs"

TARGET_DOCS = {
    "FAQ-PATENTS.pdf",
    "FAQ-TRADEMARKS.pdf",
    "FAQ-COPYRIGHTS.pdf",
    "FAQ--DESIGNS.pdf",
    "FAQ-GIS.pdf",
    "FAQ-SICLD.pdf",
}


def normalize_spaces(text: str) -> str:
    text = text.replace("\u00ad", "")
    text = text.replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n[ \t]+", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def clean_pdf_text(text: str) -> str:
    if not text:
        return ""
    text = text.replace("\u00ad", "")
    text = text.replace("\xa0", " ")
    text = text.replace("\uf0b7", "•")
    text = text.replace("\u2013", "-").replace("\u2014", "-")
    text = text.replace("\u2018", "'").replace("\u2019", "'")
    text = text.replace("\u201c", '"').replace("\u201d", '"')

    lines = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            lines.append("")
            continue
        if re.fullmatch(r"\d+", line):
            continue
        if re.fullmatch(r"Page\s+\d+", line, re.I):
            continue
        if re.fullmatch(r"\d+\s*/\s*\d+", line):
            continue
        lines.append(line)

    text = "\n".join(lines)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def load_chunks(path: Path):
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def get_page_text(pdf_path: Path, page_no: int) -> str:
    doc = fitz.open(pdf_path)
    try:
        idx = max(0, page_no - 1)
        text = doc[idx].get_text("text")
        return clean_pdf_text(text)
    finally:
        doc.close()


def get_page_window_text(pdf_path: Path, page_no: int) -> str:
    """
    Current page + next page window, taaki block page-end pe cut na ho.
    """
    doc = fitz.open(pdf_path)
    try:
        texts = []
        for idx in [page_no - 1, page_no]:
            if 0 <= idx < doc.page_count:
                texts.append(clean_pdf_text(doc[idx].get_text("text")))
        return "\n".join(t for t in texts if t).strip()
    finally:
        doc.close()


def is_suspicious(chunk: dict) -> bool:
    if chunk.get("doc_name") not in TARGET_DOCS:
        return False

    heading = normalize_spaces(chunk.get("heading") or "")
    text = chunk.get("text") or ""

    if not heading or not text:
        return False

    # Case 1: heading contains explicit A:
    if " A:" in heading or heading.endswith(" A:"):
        return True

    # Case 2: question mark ke baad declarative overflow
    if re.search(r"\?\s+(No,|Yes,|If\b|The\b|It\b|A\b|An\b|Patent\b|Trademark\b|Copyright\b|Design\b)", heading, re.I):
        return True

    # Case 3: full stop ke baad likely answer start
    if re.search(r"\.\s+(No,|Yes,|If\b|The\b|It\b|A\b|An\b|India\b)", heading, re.I):
        return True

    # Case 4: q part in text already contains answer-like continuation
    q_match = re.match(r"^Q\d+\.\s+(.*?)(?:\n\nA:|$)", text, flags=re.S)
    if q_match:
        q_body = normalize_spaces(q_match.group(1))
        if re.search(r"\?\s+(No,|Yes,|If\b|The\b|It\b|A\b|An\b)", q_body, re.I):
            return True
        if re.search(r"\.\s+(No,|Yes,|If\b|The\b|It\b|A\b|An\b|India\b)", q_body, re.I):
            return True
        if " A:" in q_body:
            return True

    return False


def extract_numbered_block(page_text: str, qno: str) -> str:
    """
    Extracts the numbered FAQ block starting from qno until next numbered question.
    """
    if not qno:
        return ""

    pattern = re.compile(
        rf"(?ms)^\s*{re.escape(str(qno))}[.)]?\s+(.*?)(?=^\s*\d{{1,3}}[.)]?\s+|\Z)"
    )
    m = pattern.search(page_text)
    if not m:
        return ""

    block = m.group(1).strip()
    return normalize_spaces(block)


ANSWER_START_LINE_RE = re.compile(
    r"^(No,|Yes,|If\b|The\b|It\b|A\b|An\b|Patent\b|Trademark\b|Copyright\b|Design\b|Geographical\b|GI\b|India\b)",
    re.I,
)


def split_question_answer_from_block(block: str):
    """
    Conservative splitter:
    1) If first line ends with ? => next lines are answer
    2) If first line doesn't end with ?, but second line starts like answer => first line question
    3) Else if block has ? and after that answer-like text begins => split there
    """
    if not block:
        return None, None

    lines = [normalize_spaces(x) for x in block.split("\n") if normalize_spaces(x)]
    if not lines:
        return None, None

    # Rule 1: first line ends with ?
    if len(lines) >= 2 and lines[0].strip().endswith("?"):
        question = lines[0].strip()
        answer = " ".join(lines[1:]).strip()
        if answer:
            return question, answer

    # Rule 2: first line + second line answer marker
    if len(lines) >= 2 and ANSWER_START_LINE_RE.match(lines[1]):
        question = lines[0].strip()
        answer = " ".join(lines[1:]).strip()
        if answer:
            return question, answer

    # Rule 3: collect question lines until a line ends with ?,
    # then remaining lines answer
    q_lines = []
    a_lines = []
    found_q_end = False

    for i, line in enumerate(lines):
        if not found_q_end:
            q_lines.append(line)
            if line.endswith("?"):
                found_q_end = True
        else:
            a_lines.append(line)

    if q_lines and a_lines:
        question = " ".join(q_lines).strip()
        answer = " ".join(a_lines).strip()
        return question, answer

    # Rule 4: inline split after ? when answer phrase follows
    merged = " ".join(lines).strip()
    m = re.match(r"^(.*?\?)\s+(No,|Yes,|If\b|The\b|It\b|A\b|An\b|Patent\b|Trademark\b|Copyright\b|Design\b|Geographical\b|GI\b|India\b)(.*)$", merged, re.I)
    if m:
        question = m.group(1).strip()
        answer = (m.group(2) + m.group(3)).strip()
        return question, answer

    # Rule 5: full stop + No/Yes style answers
    m = re.match(r"^(.*?\.)\s+(No,|Yes,|If\b|The\b|It\b|A\b|An\b|India\b)(.*)$", merged, re.I)
    if m:
        question = m.group(1).strip()
        answer = (m.group(2) + m.group(3)).strip()
        return question, answer

    return None, None


def rebuild_chunk(chunk: dict, question: str, answer: str) -> dict:
    qno = chunk.get("question_no")
    chunk["heading"] = question.strip()

    if qno:
        chunk["text"] = f"Q{qno}. {question.strip()}\n\nA: {answer.strip()}"
    else:
        chunk["text"] = f"Q. {question.strip()}\n\nA: {answer.strip()}"

    return chunk


def try_repair_chunk(chunk: dict) -> dict:
    doc_name = chunk.get("doc_name")
    qno = str(chunk.get("question_no") or "").strip()
    page_no = int(chunk.get("page_no") or chunk.get("page_start") or 1)

    pdf_path = PDF_DIR / doc_name
    if not pdf_path.exists():
        return chunk

    page_window_text = get_page_window_text(pdf_path, page_no)
    block = extract_numbered_block(page_window_text, qno)
    if not block:
        return chunk

    question, answer = split_question_answer_from_block(block)
    if not question or not answer:
        return chunk

    # extra guard: only repair if question still starts sensibly
    if len(question) < 8 or len(answer) < 12:
        return chunk

    return rebuild_chunk(chunk, question, answer)


def main():
    if not INPUT_JSONL.exists():
        raise FileNotFoundError(f"Missing input: {INPUT_JSONL}")

    chunks = load_chunks(INPUT_JSONL)

    repaired_count = 0
    suspicious_count = 0

    with open(OUTPUT_JSONL, "w", encoding="utf-8") as fout:
        for chunk in chunks:
            original = json.dumps(chunk, ensure_ascii=False)

            if is_suspicious(chunk):
                suspicious_count += 1
                repaired = try_repair_chunk(dict(chunk))
                new_dump = json.dumps(repaired, ensure_ascii=False)

                if new_dump != original:
                    repaired_count += 1
                    chunk = repaired

            fout.write(json.dumps(chunk, ensure_ascii=False) + "\n")

    print(f"[INFO] suspicious chunks found: {suspicious_count}")
    print(f"[INFO] repaired chunks: {repaired_count}")
    print(f"[DONE] output written to: {OUTPUT_JSONL}")


if __name__ == "__main__":
    main()
from __future__ import annotations

import json
import re
from pathlib import Path


INPUT_JSONL = Path("data/index/chunks.jsonl")   # apna path adjust kar lo
OUTPUT_JSONL = Path("data/index/chunks_repaired.jsonl")


def normalize_spaces(text: str) -> str:
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\s+\n", "\n", text)
    return text.strip()


def split_heading_question_and_overflow(heading: str):
    """
    Example:
    'What is a Patent? A Patent is a statutory right ...'
    =>
    question='What is a Patent?'
    overflow='A Patent is a statutory right ...'
    """
    heading = normalize_spaces(heading)
    m = re.match(r"^(.*?\?)(?:\s+(.+))?$", heading)
    if not m:
        return heading, ""

    question = (m.group(1) or "").strip()
    overflow = (m.group(2) or "").strip()
    return question, overflow


def split_text_question_answer(text: str):
    """
    Expected:
    Q1. What is a Patent? ...

    A: excluding others...
    """
    text = text.strip()
    m = re.match(r"^(Q\d+\.\s+.*?)(?:\n\s*\nA:\s*)(.*)$", text, flags=re.DOTALL)
    if m:
        q_part = m.group(1).strip()
        a_part = m.group(2).strip()
        return q_part, a_part

    # fallback
    m = re.match(r"^(Q\.\s+.*?)(?:\n\s*\nA:\s*)(.*)$", text, flags=re.DOTALL)
    if m:
        q_part = m.group(1).strip()
        a_part = m.group(2).strip()
        return q_part, a_part

    return text, ""


def clean_question_prefix(q_part: str):
    # "Q1. What is a Patent? A Patent is..." -> keep whole for now
    m = re.match(r"^(Q\d+\.\s+)(.*)$", q_part, flags=re.DOTALL)
    if m:
        return m.group(1), m.group(2).strip()

    m = re.match(r"^(Q\.\s+)(.*)$", q_part, flags=re.DOTALL)
    if m:
        return m.group(1), m.group(2).strip()

    return "Q. ", q_part.strip()


def should_repair(chunk: dict) -> bool:
    heading = (chunk.get("heading") or "").strip()
    text = (chunk.get("text") or "").strip()

    if "?" not in heading:
        return False
    if "\n\nA:" not in text:
        return False

    question, overflow = split_heading_question_and_overflow(heading)
    if not overflow:
        return False

    # repair only when overflow looks like answer text, not another question
    if "?" in overflow[:80]:
        return False

    # common sign: answer starts mid-sentence / lowercase continuation
    _, answer = split_text_question_answer(text)
    if not answer:
        return False

    first = answer[:1]
    if first and first.islower():
        return True

    # or overflow is clearly declarative answer-like
    if re.match(r"^(A|An|The|It|Patent|Trademark|Copyright|Design|Geographical|GI)\b", overflow, re.I):
        return True

    return True


def repair_chunk(chunk: dict) -> dict:
    heading = (chunk.get("heading") or "").strip()
    text = (chunk.get("text") or "").strip()
    qno = chunk.get("question_no")

    question, overflow = split_heading_question_and_overflow(heading)
    q_prefix, q_body_old = clean_question_prefix(split_text_question_answer(text)[0])
    _, answer_tail = split_text_question_answer(text)

    repaired_answer = normalize_spaces((overflow + " " + answer_tail).strip())
    repaired_heading = question.strip()

    if qno:
        repaired_text = f"Q{qno}. {repaired_heading}\n\nA: {repaired_answer}"
    else:
        repaired_text = f"{q_prefix}{repaired_heading}\n\nA: {repaired_answer}"

    chunk["heading"] = repaired_heading
    chunk["text"] = repaired_text
    return chunk


def main():
    if not INPUT_JSONL.exists():
        raise FileNotFoundError(f"Input not found: {INPUT_JSONL}")

    repaired = 0
    total = 0

    with open(INPUT_JSONL, "r", encoding="utf-8") as fin, \
         open(OUTPUT_JSONL, "w", encoding="utf-8") as fout:
        for line in fin:
            if not line.strip():
                continue
            total += 1
            chunk = json.loads(line)

            if should_repair(chunk):
                chunk = repair_chunk(chunk)
                repaired += 1

            fout.write(json.dumps(chunk, ensure_ascii=False) + "\n")

    print(f"[DONE] Total chunks: {total}")
    print(f"[DONE] Repaired chunks: {repaired}")
    print(f"[DONE] Output: {OUTPUT_JSONL}")


if __name__ == "__main__":
    main()
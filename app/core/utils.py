import re
from typing import Iterable

_whitespace_re = re.compile(r"\s+")
_heading_re = re.compile(r"^(section|chapter|rule|form|schedule|appendix|annexure)\b", re.I)


def normalize_text(text: str) -> str:
    text = text.replace("\x00", " ")
    text = _whitespace_re.sub(" ", text).strip()
    return text


def looks_like_heading(text: str) -> bool:
    if not text:
        return False
    t = text.strip()
    if len(t) > 140:
        return False
    if _heading_re.search(t):
        return True
    alpha_ratio = sum(c.isalpha() for c in t) / max(len(t), 1)
    return alpha_ratio > 0.55 and t == t.title()


def chunk_paragraphs(paragraphs: Iterable[str], target_chars: int = 900, overlap_chars: int = 160):
    chunks = []
    current = []
    current_len = 0
    for para in paragraphs:
        para = normalize_text(para)
        if not para:
            continue
        if current_len + len(para) + 1 <= target_chars:
            current.append(para)
            current_len += len(para) + 1
        else:
            if current:
                chunks.append("\n".join(current))
            if chunks and overlap_chars > 0:
                overlap_source = chunks[-1][-overlap_chars:]
                current = [overlap_source, para]
                current_len = len(overlap_source) + len(para)
            else:
                current = [para]
                current_len = len(para)
    if current:
        chunks.append("\n".join(current))
    return chunks

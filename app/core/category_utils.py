from __future__ import annotations

from typing import Iterable


DOC_CATEGORY_MAP = {
    "FAQ-PATENTS.pdf": "patent",
    "FAQ-TRADEMARKS.pdf": "trademark",
    "FAQ-COPYRIGHTS.pdf": "copyright",
    "FAQ--DESIGNS.pdf": "design",
    "FAQ-GIS.pdf": "gi",
    "FAQ-SICLD.pdf": "sicld",
}

ENTITY_ALIASES = {
    "patent": [
        "patent", "patents", "pct", "national phase",
        "patent of addition", "divisional application",
        "provisional specification", "complete specification",
    ],
    "trademark": [
        "trademark", "trade mark", "trade marks", "trademarks",
        "service mark", "collective mark", "certification mark",
        "madrid protocol", "trade dress",
    ],
    "copyright": [
        "copyright", "copyrights", "idea", "title", "slogan",
        "website", "software", "literary work", "artistic work",
        "dramatic work", "musical work",
    ],
    "design": [
        "design", "designs", "industrial design", "article", "set of articles",
    ],
    "gi": [
        "gi", "gis", "geographical indication", "geographical indications",
        "authorized user", "registered proprietor", "producer",
    ],
    "sicld": [
        "sicld", "layout design", "layout-design",
        "pcb", "printed circuit board",
        "semiconductor integrated circuit layout design",
    ],
}


VALID_CATEGORIES = {"patent", "trademark", "copyright", "design", "gi", "sicld"}


def normalize_category(value: str | None) -> str | None:
    if not value:
        return None

    value = value.strip().lower()

    if value in {"geographical indication", "geographical indications"}:
        return "gi"

    if value in VALID_CATEGORIES:
        return value

    return None


def category_from_doc_names(doc_names: Iterable[str]) -> str | None:
    for name in doc_names:
        if name in DOC_CATEGORY_MAP:
            return DOC_CATEGORY_MAP[name]
    return None


def category_from_question(question: str) -> str | None:
    q = (question or "").strip().lower()

    best_category = None
    best_len = -1

    for category, aliases in ENTITY_ALIASES.items():
        for alias in aliases:
            if alias in q and len(alias) > best_len:
                best_category = category
                best_len = len(alias)

    return best_category


def infer_category(
    question: str,
    citations: list[dict] | None = None,
    pipeline_category: str | None = None,
) -> str | None:
    norm = normalize_category(pipeline_category)
    if norm:
        return norm

    citations = citations or []
    from_docs = category_from_doc_names(
        [c.get("doc_name", "") for c in citations if c.get("doc_name")]
    )
    if from_docs:
        return from_docs

    return category_from_question(question)
from __future__ import annotations

from app.core.category_utils import infer_category, normalize_category


class CategoriesService:
    def infer(self, question: str, citations: list[dict] | None, pipeline_category: str | None) -> str | None:
        return infer_category(question, citations, pipeline_category)

    def normalize(self, category: str | None) -> str | None:
        return normalize_category(category)

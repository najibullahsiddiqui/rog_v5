from __future__ import annotations

from app.core.admin_store import AdminStore
from app.core.category_utils import infer_category, normalize_category


class CategoriesService:
    def __init__(self, store: AdminStore | None = None):
        self.store = store or AdminStore()

    def infer(self, question: str, citations: list[dict] | None, pipeline_category: str | None) -> str | None:
        inferred = infer_category(question, citations, pipeline_category)
        if inferred:
            return inferred
        return self.predict_from_question(question)

    def normalize(self, category: str | None) -> str | None:
        normalized = normalize_category(category)
        if normalized:
            return normalized
        if not category:
            return None

        query = category.strip().lower()
        for item in self.store.list_categories(include_inactive=False):
            code = str(item.get("code") or "").strip().lower()
            name = str(item.get("name") or "").strip().lower()
            if query in {code, name}:
                return code

            synonyms = self.store.list_category_synonyms(int(item["id"]))
            if any(
                str(s.get("normalized_synonym") or "").lower() == query
                or str(s.get("synonym") or "").strip().lower() == query
                for s in synonyms
            ):
                return code
        return None

    def predict_from_question(self, question: str) -> str | None:
        q = (question or "").strip().lower()
        if not q:
            return None

        categories = self.store.list_categories(include_inactive=False)
        for cat in categories:
            code = str(cat.get("code") or "").lower()
            name = str(cat.get("name") or "").lower()
            if code and code in q:
                return code
            if name and name in q:
                return code

            for syn in self.store.list_category_synonyms(int(cat["id"])):
                raw_syn = str(syn.get("synonym") or "").lower()
                if raw_syn and raw_syn in q:
                    return code
        return None

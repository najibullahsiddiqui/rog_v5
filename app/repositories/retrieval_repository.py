from __future__ import annotations

from app.core.retrieval import Retriever


class RetrievalRepository:
    def __init__(self, retriever: Retriever | None = None):
        self.retriever = retriever or Retriever()

    def retrieve(self, query: str) -> list[dict]:
        return self.retriever.retrieve(query)

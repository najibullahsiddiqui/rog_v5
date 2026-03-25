from __future__ import annotations

from app.repositories import RetrievalRepository


class RetrievalService:
    def __init__(self, repository: RetrievalRepository | None = None):
        self.repository = repository or RetrievalRepository()

    def retrieve(self, question: str) -> list[dict]:
        return self.repository.retrieve(question)

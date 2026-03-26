from __future__ import annotations

from app.repositories import AdminRepository


class ExpertAnswersService:
    def __init__(self, repository: AdminRepository | None = None):
        self.repository = repository or AdminRepository()

    def find_exact(self, question: str, normalized_question: str) -> dict | None:
        return self.repository.find_expert_answer(
            question=question,
            normalized_question=normalized_question,
        )

    def save(self, **kwargs) -> int:
        return self.repository.save_expert_answer(**kwargs)

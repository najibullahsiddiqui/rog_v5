from __future__ import annotations

from app.repositories import AdminRepository


class ChatHistoryService:
    def __init__(self, repository: AdminRepository | None = None):
        self.repository = repository or AdminRepository()

    def log_feedback(self, **kwargs) -> int:
        return self.repository.save_feedback(**kwargs)

    def list_feedback(self, category: str | None = None) -> list[dict]:
        return self.repository.list_feedback(category)

    def log_wrong_answer_report(self, **kwargs) -> int:
        return self.repository.create_wrong_answer_report(**kwargs)

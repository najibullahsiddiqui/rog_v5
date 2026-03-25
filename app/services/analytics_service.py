from __future__ import annotations

from app.repositories import AdminRepository


class AnalyticsService:
    def __init__(self, repository: AdminRepository | None = None):
        self.repository = repository or AdminRepository()

    def summary(self) -> dict:
        return self.repository.dashboard_summary()

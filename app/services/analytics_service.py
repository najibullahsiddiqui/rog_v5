from __future__ import annotations

from app.repositories import AdminRepository


class AnalyticsService:
    def __init__(self, repository: AdminRepository | None = None):
        self.repository = repository or AdminRepository()

    def summary(self) -> dict:
        return self.repository.dashboard_summary()

    def dashboard_summary(self) -> dict:
        return self.repository.dashboard_summary_v2()

    def analytics_breakdown(self, range_days: int = 30) -> dict:
        return self.repository.analytics_breakdown(range_days=range_days)

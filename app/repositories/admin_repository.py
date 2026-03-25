from __future__ import annotations

from app.core.admin_store import AdminStore


class AdminRepository:
    def __init__(self, store: AdminStore | None = None):
        self.store = store or AdminStore()

    def __getattr__(self, item):
        return getattr(self.store, item)

from __future__ import annotations

import sqlite3

from app.core.admin_store import DB_PATH
from app.core.db_migrations import apply_v2_schema


def run() -> None:
    with sqlite3.connect(DB_PATH) as conn:
        apply_v2_schema(conn)
    print(f"Applied v2 migrations to {DB_PATH}")


if __name__ == "__main__":
    run()

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.core.db_migrations import apply_v2_schema

DEFAULT_DB_PATH = ROOT_DIR / "data" / "admin_review.db"


def run(db_path: str | Path = DEFAULT_DB_PATH) -> None:
    target = Path(db_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(target) as conn:
        apply_v2_schema(conn)
    print(f"Applied v2 migrations to {target}")


if __name__ == "__main__":
    run()

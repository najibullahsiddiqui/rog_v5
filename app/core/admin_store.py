from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from app.core.pipeline import normalize_question_text
from app.core.db_migrations import apply_v2_schema


DB_PATH = Path("data/admin_review.db")


class AdminStore:
    def __init__(self, db_path: Path | str = DB_PATH):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _column_exists(self, conn: sqlite3.Connection, table: str, column: str) -> bool:
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
        return any(r["name"] == column for r in rows)

    def _init_db(self) -> None:
        with self._conn() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS unresolved_queries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    question TEXT NOT NULL,
                    normalized_question TEXT,
                    category TEXT,
                    user_selected_category TEXT,
                    answer_text TEXT,
                    reason TEXT,
                    citations_json TEXT,
                    status TEXT NOT NULL DEFAULT 'open',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS answer_feedback (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    question TEXT NOT NULL,
                    normalized_question TEXT,
                    category TEXT,
                    answer_text TEXT,
                    satisfied INTEGER NOT NULL,
                    comment TEXT,
                    citations_json TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS expert_answers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    question TEXT NOT NULL,
                    normalized_question TEXT,
                    category TEXT NOT NULL,
                    expert_answer TEXT NOT NULL,
                    source_note TEXT,
                    is_active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE INDEX IF NOT EXISTS idx_unresolved_category
                    ON unresolved_queries(category);

                CREATE INDEX IF NOT EXISTS idx_unresolved_user_selected_category
                    ON unresolved_queries(user_selected_category);

                CREATE INDEX IF NOT EXISTS idx_unresolved_status
                    ON unresolved_queries(status);

                CREATE INDEX IF NOT EXISTS idx_feedback_category
                    ON answer_feedback(category);

                CREATE INDEX IF NOT EXISTS idx_expert_question
                    ON expert_answers(question);

                CREATE INDEX IF NOT EXISTS idx_expert_normalized_question
                    ON expert_answers(normalized_question);
                """
            )

            # migration safety for older DBs
            if not self._column_exists(conn, "unresolved_queries", "user_selected_category"):
                conn.execute(
                    "ALTER TABLE unresolved_queries ADD COLUMN user_selected_category TEXT"
                )

            apply_v2_schema(conn)

    def log_unresolved_query(
        self,
        *,
        question: str,
        normalized_question: str | None,
        category: str | None,
        answer_text: str,
        reason: str,
        citations: list[dict] | None = None,
    ) -> int:
        normalized_question = normalize_question_text(normalized_question or question)

        with self._conn() as conn:
            cur = conn.execute(
                """
                INSERT INTO unresolved_queries
                (question, normalized_question, category, answer_text, reason, citations_json)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    question,
                    normalized_question,
                    category,
                    answer_text,
                    reason,
                    json.dumps(citations or [], ensure_ascii=False),
                ),
            )
            return int(cur.lastrowid)

    def update_unresolved_category(
        self,
        *,
        unresolved_query_id: int,
        user_selected_category: str,
    ) -> None:
        with self._conn() as conn:
            current = conn.execute(
                "SELECT category FROM unresolved_queries WHERE id=?",
                (unresolved_query_id,),
            ).fetchone()

            current_category = current["category"] if current else None
            final_category = current_category or user_selected_category

            conn.execute(
                """
                UPDATE unresolved_queries
                SET user_selected_category=?,
                    category=?,
                    updated_at=CURRENT_TIMESTAMP
                WHERE id=?
                """,
                (user_selected_category, final_category, unresolved_query_id),
            )

    def save_feedback(
        self,
        *,
        question: str,
        normalized_question: str | None,
        category: str | None,
        answer_text: str,
        satisfied: bool,
        comment: str | None = None,
        citations: list[dict] | None = None,
    ) -> int:
        normalized_question = normalize_question_text(normalized_question or question)

        with self._conn() as conn:
            citations_json = json.dumps(citations or [], ensure_ascii=False)
            cur = conn.execute(
                """
                INSERT INTO answer_feedback
                (question, normalized_question, category, answer_text, satisfied, comment, citations_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    question,
                    normalized_question,
                    category,
                    answer_text,
                    1 if satisfied else 0,
                    comment,
                    citations_json,
                ),
            )
            conn.execute(
                """
                INSERT INTO user_feedback
                (question, normalized_question, category, answer_text, satisfied, comment, citations_json, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'open')
                """,
                (
                    question,
                    normalized_question,
                    category,
                    answer_text,
                    1 if satisfied else 0,
                    comment,
                    citations_json,
                ),
            )
            return int(cur.lastrowid)

    def save_expert_answer(
        self,
        *,
        question: str,
        normalized_question: str | None,
        category: str,
        expert_answer: str,
        source_note: str | None = None,
        unresolved_query_id: int | None = None,
    ) -> int:
        normalized_question = normalize_question_text(normalized_question or question)

        with self._conn() as conn:
            cur = conn.execute(
                """
                INSERT INTO expert_answers
                (question, normalized_question, category, expert_answer, source_note, approval_status)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    question,
                    normalized_question,
                    category,
                    expert_answer,
                    source_note,
                    "approved",
                ),
            )

            if unresolved_query_id:
                conn.execute(
                    """
                    UPDATE unresolved_queries
                    SET status='resolved', updated_at=CURRENT_TIMESTAMP
                    WHERE id=?
                    """,
                    (unresolved_query_id,),
                )

            return int(cur.lastrowid)

    def find_expert_answer(
        self,
        *,
        question: str,
        normalized_question: str | None = None,
    ) -> dict[str, Any] | None:
        q = (question or "").strip()
        nq = normalize_question_text(normalized_question or question)

        with self._conn() as conn:
            row = conn.execute(
                """
                SELECT *
                FROM expert_answers
                WHERE is_active=1
                  AND (
                        normalized_question = ?
                        OR lower(question) = lower(?)
                      )
                ORDER BY id DESC
                LIMIT 1
                """,
                (nq, q),
            ).fetchone()

            return dict(row) if row else None

    def dashboard_summary(self) -> dict[str, Any]:
        with self._conn() as conn:
            unresolved = conn.execute(
                """
                SELECT
                    COALESCE(user_selected_category, category, 'unassigned') AS category,
                    COUNT(*) AS total
                FROM unresolved_queries
                WHERE status='open'
                GROUP BY COALESCE(user_selected_category, category, 'unassigned')
                ORDER BY total DESC
                """
            ).fetchall()

            feedback = conn.execute(
                """
                SELECT
                    COALESCE(category, 'unassigned') AS category,
                    COUNT(*) AS total,
                    SUM(CASE WHEN satisfied=1 THEN 1 ELSE 0 END) AS satisfied_count,
                    SUM(CASE WHEN satisfied=0 THEN 1 ELSE 0 END) AS unsatisfied_count
                FROM answer_feedback
                GROUP BY COALESCE(category, 'unassigned')
                ORDER BY total DESC
                """
            ).fetchall()

            totals = {
                "open_unresolved": conn.execute(
                    "SELECT COUNT(*) FROM unresolved_queries WHERE status='open'"
                ).fetchone()[0],
                "feedback_total": conn.execute(
                    "SELECT COUNT(*) FROM answer_feedback"
                ).fetchone()[0],
                "expert_answers_total": conn.execute(
                    "SELECT COUNT(*) FROM expert_answers WHERE is_active=1"
                ).fetchone()[0],
            }

        return {
            "totals": totals,
            "unresolved_by_category": [dict(r) for r in unresolved],
            "feedback_by_category": [dict(r) for r in feedback],
        }

    def list_unresolved(
        self,
        category: str | None = None,
        status: str = "open",
    ) -> list[dict[str, Any]]:
        query = """
            SELECT
                id,
                question,
                normalized_question,
                category,
                user_selected_category,
                COALESCE(user_selected_category, category) AS final_category,
                answer_text,
                reason,
                citations_json,
                status,
                created_at,
                updated_at
            FROM unresolved_queries
            WHERE 1=1
        """
        params: list[Any] = []

        if status:
            query += " AND status=?"
            params.append(status)

        if category:
            query += " AND COALESCE(user_selected_category, category)=?"
            params.append(category)

        query += " ORDER BY id DESC"

        with self._conn() as conn:
            rows = conn.execute(query, params).fetchall()

        items: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            item["citations"] = json.loads(item.get("citations_json") or "[]")
            items.append(item)
        return items

    def list_feedback(self, category: str | None = None) -> list[dict[str, Any]]:
        query = """
            SELECT
                id,
                question,
                normalized_question,
                category,
                answer_text,
                satisfied,
                comment,
                citations_json,
                created_at
            FROM answer_feedback
            WHERE 1=1
        """
        params: list[Any] = []

        if category:
            query += " AND category=?"
            params.append(category)

        query += " ORDER BY id DESC"

        with self._conn() as conn:
            rows = conn.execute(query, params).fetchall()

        items: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            item["citations"] = json.loads(item.get("citations_json") or "[]")
            items.append(item)
        return items

    def _table_exists(self, conn: sqlite3.Connection, table: str) -> bool:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (table,),
        ).fetchone()
        return bool(row)

    def dashboard_summary_v2(self) -> dict[str, Any]:
        with self._conn() as conn:
            def safe_count(table: str, where: str = "") -> int:
                if not self._table_exists(conn, table):
                    return 0
                query = f"SELECT COUNT(*) FROM {table}"
                if where:
                    query += f" WHERE {where}"
                return int(conn.execute(query).fetchone()[0])

            totals = {
                "data_sources_total": safe_count("data_sources"),
                "documents_total": safe_count("source_documents"),
                "chunks_total": safe_count("document_chunks"),
                "qna_pairs_total": safe_count("qna_pairs", "status='active'"),
                "expert_answers_total": safe_count("expert_answers", "is_active=1"),
                "unresolved_open": safe_count("unresolved_queries", "status='open'"),
                "wrong_answer_reports_open": safe_count("wrong_answer_reports", "status='open'"),
                "chats_total": safe_count("chat_sessions"),
                "recent_sessions_24h": safe_count(
                    "chat_sessions",
                    "started_at >= datetime('now', '-1 day')",
                ),
                "active_sessions": safe_count("chat_sessions", "status='active'"),
            }

            answer_mode_distribution: list[dict[str, Any]] = []
            if self._table_exists(conn, "chat_messages"):
                rows = conn.execute(
                    """
                    SELECT COALESCE(answer_mode, 'unknown') AS answer_mode, COUNT(*) AS total
                    FROM chat_messages
                    GROUP BY COALESCE(answer_mode, 'unknown')
                    ORDER BY total DESC
                    """
                ).fetchall()
                answer_mode_distribution = [dict(r) for r in rows]

            category_distribution: list[dict[str, Any]] = []
            if self._table_exists(conn, "categories") and self._table_exists(conn, "qna_pairs"):
                rows = conn.execute(
                    """
                    SELECT COALESCE(c.code, 'unassigned') AS category, COUNT(*) AS total
                    FROM qna_pairs q
                    LEFT JOIN categories c ON c.id = q.category_id
                    GROUP BY COALESCE(c.code, 'unassigned')
                    ORDER BY total DESC
                    """
                ).fetchall()
                category_distribution = [dict(r) for r in rows]

            feedback_summary = {
                "total": 0,
                "satisfied": 0,
                "unsatisfied": 0,
                "satisfaction_rate": 0.0,
            }
            feedback_table = "user_feedback" if self._table_exists(conn, "user_feedback") else "answer_feedback"
            if self._table_exists(conn, feedback_table):
                row = conn.execute(
                    f"""
                    SELECT
                        COUNT(*) AS total,
                        SUM(CASE WHEN satisfied=1 THEN 1 ELSE 0 END) AS satisfied,
                        SUM(CASE WHEN satisfied=0 THEN 1 ELSE 0 END) AS unsatisfied
                    FROM {feedback_table}
                    """
                ).fetchone()
                total = int(row["total"] or 0)
                sat = int(row["satisfied"] or 0)
                unsat = int(row["unsatisfied"] or 0)
                feedback_summary = {
                    "total": total,
                    "satisfied": sat,
                    "unsatisfied": unsat,
                    "satisfaction_rate": round((sat / total) if total else 0.0, 4),
                }

        return {
            "totals": totals,
            "answer_mode_distribution": answer_mode_distribution,
            "category_distribution": category_distribution,
            "feedback_summary": feedback_summary,
        }

    def analytics_breakdown(self, range_days: int = 30) -> dict[str, Any]:
        range_days = max(1, min(int(range_days), 365))
        with self._conn() as conn:
            def query_rows(sql: str, params: tuple = ()) -> list[dict[str, Any]]:
                rows = conn.execute(sql, params).fetchall()
                return [dict(r) for r in rows]

            chat_volume = query_rows(
                """
                SELECT date(created_at) AS bucket, COUNT(*) AS total
                FROM chat_messages
                WHERE datetime(created_at) >= datetime('now', ?)
                GROUP BY date(created_at)
                ORDER BY bucket ASC
                """,
                (f"-{range_days} day",),
            ) if self._table_exists(conn, "chat_messages") else []

            unresolved_trend = query_rows(
                """
                SELECT date(created_at) AS bucket, COUNT(*) AS total
                FROM unresolved_queries
                WHERE datetime(created_at) >= datetime('now', ?)
                GROUP BY date(created_at)
                ORDER BY bucket ASC
                """,
                (f"-{range_days} day",),
            ) if self._table_exists(conn, "unresolved_queries") else []

            wrong_answer_trend = query_rows(
                """
                SELECT date(created_at) AS bucket, COUNT(*) AS total
                FROM wrong_answer_reports
                WHERE datetime(created_at) >= datetime('now', ?)
                GROUP BY date(created_at)
                ORDER BY bucket ASC
                """,
                (f"-{range_days} day",),
            ) if self._table_exists(conn, "wrong_answer_reports") else []

            answer_mode_rate = query_rows(
                """
                SELECT COALESCE(answer_mode, 'unknown') AS answer_mode, COUNT(*) AS total
                FROM chat_messages
                WHERE datetime(created_at) >= datetime('now', ?)
                GROUP BY COALESCE(answer_mode, 'unknown')
                ORDER BY total DESC
                """,
                (f"-{range_days} day",),
            ) if self._table_exists(conn, "chat_messages") else []

            feedback_table = "user_feedback" if self._table_exists(conn, "user_feedback") else "answer_feedback"
            feedback_satisfaction_trend = query_rows(
                f"""
                SELECT
                    date(created_at) AS bucket,
                    COUNT(*) AS total,
                    SUM(CASE WHEN satisfied=1 THEN 1 ELSE 0 END) AS satisfied,
                    ROUND(CAST(SUM(CASE WHEN satisfied=1 THEN 1 ELSE 0 END) AS REAL) / COUNT(*), 4) AS satisfaction_rate
                FROM {feedback_table}
                WHERE datetime(created_at) >= datetime('now', ?)
                GROUP BY date(created_at)
                ORDER BY bucket ASC
                """,
                (f"-{range_days} day",),
            ) if self._table_exists(conn, feedback_table) else []

            top_categories = query_rows(
                """
                SELECT COALESCE(c.code, 'unassigned') AS category, COUNT(*) AS total
                FROM chat_messages m
                LEFT JOIN categories c ON c.id = m.category_id
                WHERE datetime(m.created_at) >= datetime('now', ?)
                GROUP BY COALESCE(c.code, 'unassigned')
                ORDER BY total DESC
                LIMIT 10
                """,
                (f"-{range_days} day",),
            ) if self._table_exists(conn, "chat_messages") and self._table_exists(conn, "categories") else []

            top_repeated_queries = query_rows(
                """
                SELECT COALESCE(normalized_question, lower(trim(question_text))) AS query, COUNT(*) AS total
                FROM chat_messages
                WHERE question_text IS NOT NULL
                  AND datetime(created_at) >= datetime('now', ?)
                GROUP BY COALESCE(normalized_question, lower(trim(question_text)))
                HAVING COUNT(*) > 1
                ORDER BY total DESC
                LIMIT 10
                """,
                (f"-{range_days} day",),
            ) if self._table_exists(conn, "chat_messages") else []

            top_failed_queries = query_rows(
                """
                SELECT COALESCE(normalized_question, lower(trim(question))) AS query, COUNT(*) AS total
                FROM unresolved_queries
                WHERE datetime(created_at) >= datetime('now', ?)
                GROUP BY COALESCE(normalized_question, lower(trim(question)))
                ORDER BY total DESC
                LIMIT 10
                """,
                (f"-{range_days} day",),
            ) if self._table_exists(conn, "unresolved_queries") else []

            source_contribution = query_rows(
                """
                SELECT COALESCE(sd.file_name, 'unknown') AS source, COUNT(*) AS total
                FROM message_citations mc
                LEFT JOIN source_documents sd ON sd.id = mc.source_document_id
                GROUP BY COALESCE(sd.file_name, 'unknown')
                ORDER BY total DESC
                LIMIT 10
                """
            ) if self._table_exists(conn, "message_citations") else []

            latency_metrics = {
                "avg_ms": None,
                "p95_ms": None,
                "sample_size": 0,
            }
            if self._table_exists(conn, "chat_messages") and self._column_exists(conn, "chat_messages", "latency_ms"):
                row = conn.execute(
                    """
                    SELECT AVG(latency_ms) AS avg_ms, COUNT(*) AS sample_size
                    FROM chat_messages
                    WHERE latency_ms IS NOT NULL
                      AND datetime(created_at) >= datetime('now', ?)
                    """,
                    (f"-{range_days} day",),
                ).fetchone()
                latency_metrics["avg_ms"] = row["avg_ms"]
                latency_metrics["sample_size"] = int(row["sample_size"] or 0)

        return {
            "range_days": range_days,
            "chat_volume": chat_volume,
            "unresolved_trend": unresolved_trend,
            "wrong_answer_trend": wrong_answer_trend,
            "answer_mode_rate": answer_mode_rate,
            "feedback_satisfaction_trend": feedback_satisfaction_trend,
            "top_categories": top_categories,
            "top_repeated_queries": top_repeated_queries,
            "top_failed_queries": top_failed_queries,
            "source_contribution": source_contribution,
            "latency_metrics": latency_metrics,
        }

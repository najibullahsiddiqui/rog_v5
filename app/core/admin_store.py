from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any

from app.core.pipeline import normalize_question_text
from app.core.db_migrations import apply_v2_schema
from app.core.config import PDF_DIR


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
            self._ensure_data_source_columns(conn)

    def _ensure_data_source_columns(self, conn: sqlite3.Connection) -> None:
        if not self._table_exists(conn, "data_sources"):
            return

        if not self._column_exists(conn, "data_sources", "source_format"):
            conn.execute(
                "ALTER TABLE data_sources ADD COLUMN source_format TEXT DEFAULT 'pdf'"
            )

        if not self._column_exists(conn, "data_sources", "last_ingestion_status"):
            conn.execute(
                "ALTER TABLE data_sources ADD COLUMN last_ingestion_status TEXT DEFAULT 'never'"
            )

        if not self._column_exists(conn, "data_sources", "last_ingestion_at"):
            conn.execute(
                "ALTER TABLE data_sources ADD COLUMN last_ingestion_at TEXT"
            )

    def _ensure_default_pdf_source(self, conn: sqlite3.Connection) -> int | None:
        if not self._table_exists(conn, "data_sources"):
            return None

        row = conn.execute(
            """
            SELECT id
            FROM data_sources
            WHERE source_key='local_pdf_folder'
            LIMIT 1
            """
        ).fetchone()
        if row:
            return int(row["id"])

        cur = conn.execute(
            """
            INSERT INTO data_sources (
                source_key, name, source_type, source_format, status, uri, last_ingestion_status
            )
            VALUES ('local_pdf_folder', 'Local PDF Folder', 'pdf_folder', 'pdf', 'enabled', ?, 'unknown')
            """,
            (str(PDF_DIR),),
        )
        return int(cur.lastrowid)

    def _sync_pdf_documents(self, conn: sqlite3.Connection) -> None:
        source_id = self._ensure_default_pdf_source(conn)
        if not source_id or not self._table_exists(conn, "source_documents"):
            return

        for pdf_path in sorted(PDF_DIR.glob("*.pdf")):
            row = conn.execute(
                """
                SELECT id FROM source_documents
                WHERE data_source_id=? AND file_name=?
                LIMIT 1
                """,
                (source_id, pdf_path.name),
            ).fetchone()
            if row:
                continue

            doc_key = f"pdf::{pdf_path.stem}"
            conn.execute(
                """
                INSERT INTO source_documents (
                    data_source_id, doc_key, file_name, version, content_hash, chunk_count, status, ingested_at
                )
                VALUES (?, ?, ?, NULL, NULL, 0, 'active', NULL)
                """,
                (source_id, doc_key, pdf_path.name),
            )

    def list_data_sources(self) -> list[dict[str, Any]]:
        with self._conn() as conn:
            self._ensure_data_source_columns(conn)
            self._sync_pdf_documents(conn)

            rows = conn.execute(
                """
                SELECT
                    ds.id,
                    ds.source_key,
                    ds.name,
                    ds.source_type,
                    COALESCE(ds.source_format, 'unknown') AS source_format,
                    ds.status,
                    ds.uri,
                    COALESCE(ds.last_ingestion_status, 'never') AS last_ingestion_status,
                    ds.last_ingestion_at,
                    ds.created_at,
                    ds.updated_at,
                    COUNT(sd.id) AS document_count,
                    COALESCE(SUM(sd.chunk_count), 0) AS chunk_count
                FROM data_sources ds
                LEFT JOIN source_documents sd
                    ON sd.data_source_id = ds.id
                    AND COALESCE(sd.status, 'active') != 'deleted'
                GROUP BY ds.id
                ORDER BY ds.id DESC
                """
            ).fetchall()
            return [dict(r) for r in rows]

    def create_data_source(
        self,
        *,
        name: str,
        source_type: str,
        source_format: str,
        uri: str | None = None,
    ) -> int:
        source_key = normalize_question_text(name).replace(" ", "_")[:48] or "source"
        source_key = f"{source_key}_{source_format}_{int(time.time() * 1000)}"

        with self._conn() as conn:
            self._ensure_data_source_columns(conn)
            cur = conn.execute(
                """
                INSERT INTO data_sources (
                    source_key, name, source_type, source_format, status, uri, last_ingestion_status
                )
                VALUES (?, ?, ?, ?, 'enabled', ?, 'never')
                """,
                (source_key, name, source_type, source_format, uri),
            )
            return int(cur.lastrowid)

    def set_data_source_status(self, data_source_id: int, status: str) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                UPDATE data_sources
                SET status=?, updated_at=CURRENT_TIMESTAMP
                WHERE id=?
                """,
                (status, data_source_id),
            )

    def list_source_documents(self, data_source_id: int) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT
                    id,
                    data_source_id,
                    doc_key,
                    file_name,
                    version,
                    content_hash,
                    chunk_count,
                    status,
                    ingested_at,
                    created_at,
                    updated_at
                FROM source_documents
                WHERE data_source_id=?
                ORDER BY file_name ASC
                """,
                (data_source_id,),
            ).fetchall()
            return [dict(r) for r in rows]

    def queue_reingest(self, data_source_id: int, trigger_type: str = "manual") -> int:
        with self._conn() as conn:
            cur = conn.execute(
                """
                INSERT INTO ingestion_jobs (data_source_id, status, trigger_type, started_at)
                VALUES (?, 'queued', ?, CURRENT_TIMESTAMP)
                """,
                (data_source_id, trigger_type),
            )

            conn.execute(
                """
                UPDATE data_sources
                SET last_ingestion_status='queued',
                    last_ingestion_at=CURRENT_TIMESTAMP,
                    updated_at=CURRENT_TIMESTAMP
                WHERE id=?
                """,
                (data_source_id,),
            )
            return int(cur.lastrowid)

    def log_import_audit(
        self,
        *,
        action: str,
        target: str,
        status: str,
        created_count: int,
        error_count: int,
        metadata: dict[str, Any] | None = None,
    ) -> int:
        with self._conn() as conn:
            cur = conn.execute(
                """
                INSERT INTO audit_logs (
                    actor_type, actor_id, action, entity_type, entity_id,
                    before_json, after_json, metadata_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "admin",
                    "web",
                    action,
                    target,
                    status,
                    None,
                    json.dumps(
                        {
                            "created_count": created_count,
                            "error_count": error_count,
                        },
                        ensure_ascii=False,
                    ),
                    json.dumps(metadata or {}, ensure_ascii=False),
                ),
            )
            return int(cur.lastrowid)

    def _get_or_create_category_id(
        self,
        conn: sqlite3.Connection,
        *,
        code: str,
        name: str | None = None,
        description: str | None = None,
    ) -> int:
        row = conn.execute(
            "SELECT id FROM categories WHERE code=? LIMIT 1",
            (code,),
        ).fetchone()
        if row:
            return int(row["id"])

        cur = conn.execute(
            """
            INSERT INTO categories (code, name, description, is_active)
            VALUES (?, ?, ?, 1)
            """,
            (code, name or code.title(), description),
        )
        return int(cur.lastrowid)

    def import_categories(self, records: list[dict[str, Any]]) -> tuple[int, list[str]]:
        errors: list[str] = []
        created = 0
        with self._conn() as conn:
            for idx, record in enumerate(records):
                code = normalize_question_text(str(record.get("code") or "")).replace(" ", "_")
                name = str(record.get("name") or "").strip()
                description = str(record.get("description") or "").strip() or None

                if not code or not name:
                    errors.append(f"Row {idx + 1}: 'code' and 'name' are required")
                    continue

                existing = conn.execute(
                    "SELECT id FROM categories WHERE code=?",
                    (code,),
                ).fetchone()
                if existing:
                    conn.execute(
                        """
                        UPDATE categories
                        SET name=?, description=?, updated_at=CURRENT_TIMESTAMP
                        WHERE code=?
                        """,
                        (name, description, code),
                    )
                else:
                    conn.execute(
                        """
                        INSERT INTO categories(code, name, description, is_active)
                        VALUES (?, ?, ?, 1)
                        """,
                        (code, name, description),
                    )
                    created += 1

        return created, errors

    def import_qna_pairs(self, records: list[dict[str, Any]]) -> tuple[int, list[str]]:
        errors: list[str] = []
        created = 0
        with self._conn() as conn:
            for idx, record in enumerate(records):
                question = str(record.get("question") or "").strip()
                answer = str(record.get("answer") or "").strip()
                category_code = normalize_question_text(str(record.get("category") or "")).replace(" ", "_")

                if not question or not answer:
                    errors.append(f"Row {idx + 1}: 'question' and 'answer' are required")
                    continue

                category_id = None
                if category_code:
                    category_id = self._get_or_create_category_id(
                        conn,
                        code=category_code,
                    )

                conn.execute(
                    """
                    INSERT INTO qna_pairs (
                        category_id, source_document_id, question, normalized_question, answer,
                        is_exact_eligible, is_semantic_eligible, status, source_note, created_by
                    )
                    VALUES (?, NULL, ?, ?, ?, ?, ?, 'active', ?, 'json_import')
                    """,
                    (
                        category_id,
                        question,
                        normalize_question_text(question),
                        answer,
                        1 if record.get("is_exact_eligible", True) else 0,
                        1 if record.get("is_semantic_eligible", True) else 0,
                        str(record.get("source_note") or "json_import"),
                    ),
                )
                created += 1

        return created, errors

    def import_decision_trees(self, records: list[dict[str, Any]]) -> tuple[int, list[str]]:
        errors: list[str] = []
        created = 0
        with self._conn() as conn:
            for idx, record in enumerate(records):
                name = str(record.get("name") or "").strip()
                nodes = record.get("nodes") or []
                edges = record.get("edges") or []
                if not name or not isinstance(nodes, list):
                    errors.append(f"Row {idx + 1}: 'name' and list 'nodes' are required")
                    continue

                category_code = normalize_question_text(str(record.get("category") or "")).replace(" ", "_")
                category_id = None
                if category_code:
                    category_id = self._get_or_create_category_id(conn, code=category_code)

                tree_key = normalize_question_text(str(record.get("tree_key") or name)).replace(" ", "_")
                tree_key = f"{tree_key}_{idx + 1}"
                cur = conn.execute(
                    """
                    INSERT INTO decision_trees (
                        tree_key, category_id, name, version, status, description, created_by
                    )
                    VALUES (?, ?, ?, ?, ?, ?, 'json_import')
                    """,
                    (
                        tree_key,
                        category_id,
                        name,
                        str(record.get("version") or "1.0.0"),
                        str(record.get("status") or "draft"),
                        str(record.get("description") or "") or None,
                    ),
                )
                tree_id = int(cur.lastrowid)

                node_id_by_key: dict[str, int] = {}
                for n in nodes:
                    node_key = str(n.get("node_key") or "").strip()
                    node_type = str(n.get("node_type") or "question").strip()
                    if not node_key:
                        continue
                    ncur = conn.execute(
                        """
                        INSERT INTO decision_tree_nodes (
                            tree_id, node_key, node_type, prompt_text, answer_text, metadata_json, is_terminal
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            tree_id,
                            node_key,
                            node_type,
                            str(n.get("prompt_text") or "") or None,
                            str(n.get("answer_text") or "") or None,
                            json.dumps(n.get("metadata") or {}, ensure_ascii=False),
                            1 if n.get("is_terminal") else 0,
                        ),
                    )
                    node_id_by_key[node_key] = int(ncur.lastrowid)

                for e in edges:
                    from_key = str(e.get("from_node_key") or "").strip()
                    to_key = str(e.get("to_node_key") or "").strip()
                    if not from_key or not to_key:
                        continue
                    from_id = node_id_by_key.get(from_key)
                    to_id = node_id_by_key.get(to_key)
                    if not from_id or not to_id:
                        continue
                    conn.execute(
                        """
                        INSERT INTO decision_tree_edges (
                            tree_id, from_node_id, to_node_id, condition_type, condition_value, priority
                        )
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (
                            tree_id,
                            from_id,
                            to_id,
                            str(e.get("condition_type") or "option"),
                            str(e.get("condition_value") or "") or None,
                            int(e.get("priority") or 0),
                        ),
                    )

                created += 1

        return created, errors

    def import_knowledge_docs(self, records: list[dict[str, Any]]) -> tuple[int, list[str]]:
        errors: list[str] = []
        created = 0
        with self._conn() as conn:
            source_id = self._ensure_default_pdf_source(conn)
            if not source_id:
                errors.append("Knowledge docs import unavailable: missing data_sources table")
                return 0, errors

            for idx, record in enumerate(records):
                title = str(record.get("title") or record.get("file_name") or "").strip()
                content = str(record.get("content") or "").strip()
                if not title or not content:
                    errors.append(f"Row {idx + 1}: 'title' (or file_name) and 'content' are required")
                    continue

                doc_key = f"json_doc::{normalize_question_text(title).replace(' ', '_')}_{idx + 1}"
                cur = conn.execute(
                    """
                    INSERT INTO source_documents (
                        data_source_id, doc_key, file_name, version, content_hash, chunk_count, status, metadata_json, ingested_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, 'active', ?, CURRENT_TIMESTAMP)
                    """,
                    (
                        source_id,
                        doc_key,
                        f"{title}.json",
                        str(record.get("version") or "") or None,
                        str(record.get("content_hash") or "") or None,
                        1,
                        json.dumps({"origin": "json_convert", "source_type": "knowledge_doc"}, ensure_ascii=False),
                    ),
                )
                source_document_id = int(cur.lastrowid)

                conn.execute(
                    """
                    INSERT INTO document_chunks (
                        source_document_id, chunk_key, chunk_index, normalized_text, text, metadata_json
                    )
                    VALUES (?, ?, 0, ?, ?, ?)
                    """,
                    (
                        source_document_id,
                        f"{doc_key}::chunk0",
                        normalize_question_text(content),
                        content,
                        json.dumps({"title": title}, ensure_ascii=False),
                    ),
                )
                created += 1

        return created, errors

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

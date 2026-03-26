from __future__ import annotations

import json
import re
import sqlite3
import time
from difflib import SequenceMatcher
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
            self._ensure_qna_pair_columns(conn)
            self._ensure_category_columns(conn)
            self._ensure_decision_tree_columns(conn)
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS tree_runtime_sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_key TEXT NOT NULL,
                    tree_id INTEGER NOT NULL,
                    current_node_key TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'active',
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(session_key),
                    FOREIGN KEY (tree_id) REFERENCES decision_trees(id)
                )
                """
            )

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

    def _ensure_qna_pair_columns(self, conn: sqlite3.Connection) -> None:
        if not self._table_exists(conn, "qna_pairs"):
            return

        if not self._column_exists(conn, "qna_pairs", "approval_status"):
            conn.execute(
                "ALTER TABLE qna_pairs ADD COLUMN approval_status TEXT DEFAULT 'approved'"
            )

        if not self._column_exists(conn, "qna_pairs", "priority"):
            conn.execute(
                "ALTER TABLE qna_pairs ADD COLUMN priority INTEGER DEFAULT 0"
            )

    def _ensure_category_columns(self, conn: sqlite3.Connection) -> None:
        if not self._table_exists(conn, "categories"):
            return

        if not self._column_exists(conn, "categories", "display_order"):
            conn.execute(
                "ALTER TABLE categories ADD COLUMN display_order INTEGER DEFAULT 0"
            )

        if not self._column_exists(conn, "categories", "routing_hint"):
            conn.execute(
                "ALTER TABLE categories ADD COLUMN routing_hint TEXT"
            )

        if not self._column_exists(conn, "categories", "prompt_hint"):
            conn.execute(
                "ALTER TABLE categories ADD COLUMN prompt_hint TEXT"
            )

        if not self._column_exists(conn, "categories", "retrieval_scope_json"):
            conn.execute(
                "ALTER TABLE categories ADD COLUMN retrieval_scope_json TEXT"
            )

    def _ensure_decision_tree_columns(self, conn: sqlite3.Connection) -> None:
        if not self._table_exists(conn, "decision_trees"):
            return
        if not self._column_exists(conn, "decision_trees", "is_active"):
            conn.execute(
                "ALTER TABLE decision_trees ADD COLUMN is_active INTEGER DEFAULT 1"
            )
        if not self._column_exists(conn, "decision_trees", "trigger_phrases_json"):
            conn.execute(
                "ALTER TABLE decision_trees ADD COLUMN trigger_phrases_json TEXT"
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

    def list_categories(self, include_inactive: bool = True) -> list[dict[str, Any]]:
        with self._conn() as conn:
            self._ensure_category_columns(conn)
            query = """
                SELECT
                    c.id,
                    c.code,
                    c.name,
                    c.description,
                    c.is_active,
                    COALESCE(c.display_order, 0) AS display_order,
                    c.routing_hint,
                    c.prompt_hint,
                    c.retrieval_scope_json,
                    c.created_at,
                    c.updated_at,
                    COUNT(DISTINCT s.id) AS synonyms_count
                FROM categories c
                LEFT JOIN category_synonyms s ON s.category_id = c.id
            """
            if not include_inactive:
                query += " WHERE c.is_active=1"

            query += """
                GROUP BY c.id
                ORDER BY c.is_active DESC, COALESCE(c.display_order, 0) ASC, c.name ASC
            """
            rows = conn.execute(query).fetchall()
            items = [dict(r) for r in rows]
            for item in items:
                item["retrieval_scope"] = json.loads(item.get("retrieval_scope_json") or "{}")
            return items

    def create_category(
        self,
        *,
        code: str,
        name: str,
        description: str | None = None,
        display_order: int = 0,
        routing_hint: str | None = None,
        prompt_hint: str | None = None,
        retrieval_scope: dict[str, Any] | None = None,
        is_active: bool = True,
    ) -> int:
        code = normalize_question_text(code).replace(" ", "_")
        with self._conn() as conn:
            self._ensure_category_columns(conn)
            cur = conn.execute(
                """
                INSERT INTO categories(
                    code, name, description, is_active, display_order, routing_hint, prompt_hint, retrieval_scope_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    code,
                    name.strip(),
                    description,
                    1 if is_active else 0,
                    int(display_order),
                    routing_hint,
                    prompt_hint,
                    json.dumps(retrieval_scope or {}, ensure_ascii=False),
                ),
            )
            return int(cur.lastrowid)

    def update_category(self, category_id: int, payload: dict[str, Any]) -> bool:
        with self._conn() as conn:
            self._ensure_category_columns(conn)
            cur = conn.execute(
                """
                UPDATE categories
                SET code=?,
                    name=?,
                    description=?,
                    is_active=?,
                    display_order=?,
                    routing_hint=?,
                    prompt_hint=?,
                    retrieval_scope_json=?,
                    updated_at=CURRENT_TIMESTAMP
                WHERE id=?
                """,
                (
                    normalize_question_text(str(payload.get("code") or "")).replace(" ", "_"),
                    str(payload.get("name") or "").strip(),
                    str(payload.get("description") or "") or None,
                    1 if payload.get("is_active", True) else 0,
                    int(payload.get("display_order") or 0),
                    str(payload.get("routing_hint") or "") or None,
                    str(payload.get("prompt_hint") or "") or None,
                    json.dumps(payload.get("retrieval_scope") or {}, ensure_ascii=False),
                    category_id,
                ),
            )
            return cur.rowcount > 0

    def archive_category(self, category_id: int) -> bool:
        with self._conn() as conn:
            cur = conn.execute(
                "UPDATE categories SET is_active=0, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (category_id,),
            )
            return cur.rowcount > 0

    def list_category_synonyms(self, category_id: int) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT id, category_id, synonym, normalized_synonym, created_at
                FROM category_synonyms
                WHERE category_id=?
                ORDER BY synonym ASC
                """,
                (category_id,),
            ).fetchall()
            return [dict(r) for r in rows]

    def add_category_synonym(self, category_id: int, synonym: str) -> int:
        synonym = (synonym or "").strip()
        if not synonym:
            raise ValueError("synonym is required")
        with self._conn() as conn:
            cur = conn.execute(
                """
                INSERT OR IGNORE INTO category_synonyms(category_id, synonym, normalized_synonym)
                VALUES (?, ?, ?)
                """,
                (category_id, synonym, normalize_question_text(synonym)),
            )
            return int(cur.lastrowid or 0)

    def category_statistics(self) -> dict[str, Any]:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT
                    c.id,
                    c.code,
                    c.name,
                    c.is_active,
                    COUNT(DISTINCT q.id) AS qna_pairs_total,
                    SUM(CASE WHEN q.status='active' THEN 1 ELSE 0 END) AS qna_active,
                    SUM(CASE WHEN q.status='archived' THEN 1 ELSE 0 END) AS qna_archived,
                    COUNT(DISTINCT uq.id) AS unresolved_total
                FROM categories c
                LEFT JOIN qna_pairs q ON q.category_id = c.id
                LEFT JOIN unresolved_queries uq ON uq.category = c.code
                GROUP BY c.id
                ORDER BY COALESCE(c.display_order, 0) ASC, c.name ASC
                """
            ).fetchall()
            return {"items": [dict(r) for r in rows]}

    def list_decision_trees(self, include_inactive: bool = True) -> list[dict[str, Any]]:
        with self._conn() as conn:
            self._ensure_decision_tree_columns(conn)
            query = """
                SELECT
                    dt.id,
                    dt.tree_key,
                    dt.name,
                    dt.version,
                    dt.status,
                    dt.description,
                    dt.is_active,
                    dt.trigger_phrases_json,
                    c.code AS category_code,
                    dt.created_at,
                    dt.updated_at,
                    COUNT(DISTINCT n.id) AS nodes_count,
                    COUNT(DISTINCT e.id) AS edges_count
                FROM decision_trees dt
                LEFT JOIN categories c ON c.id = dt.category_id
                LEFT JOIN decision_tree_nodes n ON n.tree_id = dt.id
                LEFT JOIN decision_tree_edges e ON e.tree_id = dt.id
            """
            if not include_inactive:
                query += " WHERE dt.is_active=1"
            query += " GROUP BY dt.id ORDER BY dt.updated_at DESC"
            rows = conn.execute(query).fetchall()
            items = [dict(r) for r in rows]
            for item in items:
                item["trigger_phrases"] = json.loads(item.get("trigger_phrases_json") or "[]")
            return items

    def get_decision_tree(self, tree_id: int) -> dict[str, Any] | None:
        with self._conn() as conn:
            self._ensure_decision_tree_columns(conn)
            tree = conn.execute(
                """
                SELECT dt.*, c.code AS category_code
                FROM decision_trees dt
                LEFT JOIN categories c ON c.id = dt.category_id
                WHERE dt.id=?
                """,
                (tree_id,),
            ).fetchone()
            if not tree:
                return None

            nodes = conn.execute(
                """
                SELECT id, node_key, node_type, prompt_text, answer_text, metadata_json, is_terminal
                FROM decision_tree_nodes
                WHERE tree_id=?
                ORDER BY id ASC
                """,
                (tree_id,),
            ).fetchall()
            edges = conn.execute(
                """
                SELECT e.id, fn.node_key AS from_node_key, tn.node_key AS to_node_key,
                       e.condition_type, e.condition_value, e.priority
                FROM decision_tree_edges e
                JOIN decision_tree_nodes fn ON fn.id = e.from_node_id
                JOIN decision_tree_nodes tn ON tn.id = e.to_node_id
                WHERE e.tree_id=?
                ORDER BY e.priority ASC, e.id ASC
                """,
                (tree_id,),
            ).fetchall()
            result = dict(tree)
            result["trigger_phrases"] = json.loads(result.get("trigger_phrases_json") or "[]")
            result["nodes"] = [dict(r) for r in nodes]
            result["edges"] = [dict(r) for r in edges]
            return result

    def save_decision_tree(self, payload: dict[str, Any]) -> int:
        tree_id = int(payload.get("id") or 0)
        nodes = payload.get("nodes") or []
        edges = payload.get("edges") or []
        category_code = normalize_question_text(str(payload.get("category_code") or "")).replace(" ", "_")

        with self._conn() as conn:
            self._ensure_decision_tree_columns(conn)
            category_id = None
            if category_code:
                category_id = self._get_or_create_category_id(conn, code=category_code)

            if tree_id:
                conn.execute(
                    """
                    UPDATE decision_trees
                    SET tree_key=?, name=?, version=?, status=?, description=?,
                        category_id=?, is_active=?, trigger_phrases_json=?, updated_at=CURRENT_TIMESTAMP
                    WHERE id=?
                    """,
                    (
                        normalize_question_text(str(payload.get("tree_key") or payload.get("name") or "")).replace(" ", "_"),
                        str(payload.get("name") or "").strip(),
                        str(payload.get("version") or "1.0.0"),
                        str(payload.get("status") or "draft"),
                        str(payload.get("description") or "") or None,
                        category_id,
                        1 if payload.get("is_active", True) else 0,
                        json.dumps(payload.get("trigger_phrases") or [], ensure_ascii=False),
                        tree_id,
                    ),
                )
                conn.execute("DELETE FROM decision_tree_edges WHERE tree_id=?", (tree_id,))
                conn.execute("DELETE FROM decision_tree_nodes WHERE tree_id=?", (tree_id,))
            else:
                cur = conn.execute(
                    """
                    INSERT INTO decision_trees (
                        tree_key, category_id, name, version, status, description, created_by, is_active, trigger_phrases_json
                    )
                    VALUES (?, ?, ?, ?, ?, ?, 'admin_ui', ?, ?)
                    """,
                    (
                        normalize_question_text(str(payload.get("tree_key") or payload.get("name") or "")).replace(" ", "_"),
                        category_id,
                        str(payload.get("name") or "").strip(),
                        str(payload.get("version") or "1.0.0"),
                        str(payload.get("status") or "draft"),
                        str(payload.get("description") or "") or None,
                        1 if payload.get("is_active", True) else 0,
                        json.dumps(payload.get("trigger_phrases") or [], ensure_ascii=False),
                    ),
                )
                tree_id = int(cur.lastrowid)

            node_id_by_key: dict[str, int] = {}
            for n in nodes:
                node_key = str(n.get("node_key") or "").strip()
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
                        str(n.get("node_type") or "question"),
                        str(n.get("prompt_text") or "") or None,
                        str(n.get("answer_text") or "") or None,
                        json.dumps(n.get("metadata") or {}, ensure_ascii=False),
                        1 if n.get("is_terminal") else 0,
                    ),
                )
                node_id_by_key[node_key] = int(ncur.lastrowid)

            for e in edges:
                from_id = node_id_by_key.get(str(e.get("from_node_key") or "").strip())
                to_id = node_id_by_key.get(str(e.get("to_node_key") or "").strip())
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
            return tree_id

    def delete_decision_tree(self, tree_id: int) -> bool:
        with self._conn() as conn:
            conn.execute("DELETE FROM decision_tree_edges WHERE tree_id=?", (tree_id,))
            conn.execute("DELETE FROM decision_tree_nodes WHERE tree_id=?", (tree_id,))
            cur = conn.execute("DELETE FROM decision_trees WHERE id=?", (tree_id,))
            return cur.rowcount > 0

    def run_decision_tree(self, session_key: str, question: str) -> dict[str, Any] | None:
        skey = (session_key or "").strip() or "default_session"
        q = (question or "").strip().lower()
        if not q:
            return None

        with self._conn() as conn:
            self._ensure_decision_tree_columns(conn)
            session = conn.execute(
                "SELECT * FROM tree_runtime_sessions WHERE session_key=? AND status='active' LIMIT 1",
                (skey,),
            ).fetchone()

            tree_id = None
            current_node_key = None
            if session:
                tree_id = int(session["tree_id"])
                current_node_key = str(session["current_node_key"])
            else:
                trees = conn.execute(
                    """
                    SELECT id, trigger_phrases_json
                    FROM decision_trees
                    WHERE is_active=1
                    ORDER BY updated_at DESC
                    """
                ).fetchall()
                for t in trees:
                    phrases = json.loads(t["trigger_phrases_json"] or "[]")
                    if any(str(p).strip().lower() in q for p in phrases):
                        tree_id = int(t["id"])
                        break
                if not tree_id:
                    return None

                first_node = conn.execute(
                    "SELECT node_key FROM decision_tree_nodes WHERE tree_id=? ORDER BY id ASC LIMIT 1",
                    (tree_id,),
                ).fetchone()
                if not first_node:
                    return None
                current_node_key = str(first_node["node_key"])
                conn.execute(
                    """
                    INSERT OR REPLACE INTO tree_runtime_sessions(session_key, tree_id, current_node_key, status, updated_at)
                    VALUES (?, ?, ?, 'active', CURRENT_TIMESTAMP)
                    """,
                    (skey, tree_id, current_node_key),
                )

            node = conn.execute(
                """
                SELECT id, node_key, prompt_text, answer_text, metadata_json, is_terminal
                FROM decision_tree_nodes
                WHERE tree_id=? AND node_key=?
                LIMIT 1
                """,
                (tree_id, current_node_key),
            ).fetchone()
            if not node:
                return None

            edges = conn.execute(
                """
                SELECT e.*, tn.node_key AS to_node_key
                FROM decision_tree_edges e
                JOIN decision_tree_nodes fn ON fn.id=e.from_node_id
                JOIN decision_tree_nodes tn ON tn.id=e.to_node_id
                WHERE e.tree_id=? AND fn.node_key=?
                ORDER BY e.priority ASC, e.id ASC
                """,
                (tree_id, current_node_key),
            ).fetchall()

            selected_edge = self._best_matching_edge(edges, q)
            if not selected_edge and edges:
                selected_edge = edges[0]

            if selected_edge:
                next_key = str(selected_edge["to_node_key"])
                conn.execute(
                    "UPDATE tree_runtime_sessions SET current_node_key=?, updated_at=CURRENT_TIMESTAMP WHERE session_key=?",
                    (next_key, skey),
                )
                next_node = conn.execute(
                    "SELECT node_key, prompt_text, answer_text, metadata_json, is_terminal FROM decision_tree_nodes WHERE tree_id=? AND node_key=? LIMIT 1",
                    (tree_id, next_key),
                ).fetchone()
            else:
                next_node = node

            if not next_node:
                return None

            metadata = json.loads(next_node["metadata_json"] or "{}")
            is_terminal = int(next_node["is_terminal"] or 0) == 1
            if not is_terminal:
                options = [str(e["condition_value"] or "").strip() for e in edges if str(e["condition_value"] or "").strip()]
                return {
                    "type": "prompt",
                    "tree_id": tree_id,
                    "node_key": next_node["node_key"],
                    "prompt": str(next_node["prompt_text"] or "Please choose an option."),
                    "options": options,
                }

            conn.execute(
                "UPDATE tree_runtime_sessions SET status='completed', updated_at=CURRENT_TIMESTAMP WHERE session_key=?",
                (skey,),
            )
            outcome_type = str(metadata.get("outcome_type") or "final_answer")
            outcome_value = metadata.get("outcome_value")
            return {
                "type": "terminal",
                "tree_id": tree_id,
                "node_key": next_node["node_key"],
                "outcome_type": outcome_type,
                "outcome_value": outcome_value,
                "answer_text": str(next_node["answer_text"] or ""),
            }

    def _normalize_for_match(self, text: str) -> str:
        return normalize_question_text(re.sub(r"[/|,;]+", " ", text or "")).strip()

    def _token_overlap_score(self, a: str, b: str) -> float:
        a_tokens = {t for t in self._normalize_for_match(a).split() if t}
        b_tokens = {t for t in self._normalize_for_match(b).split() if t}
        if not a_tokens or not b_tokens:
            return 0.0
        return len(a_tokens & b_tokens) / max(1, len(a_tokens | b_tokens))

    def _edge_match_score(self, condition_value: str, user_text: str) -> float:
        cond = self._normalize_for_match(condition_value)
        query = self._normalize_for_match(user_text)
        if not cond or not query:
            return 0.0

        if query == cond:
            return 1.0
        if query.startswith(cond) or query.endswith(cond):
            return 0.94
        if cond in query:
            return 0.88

        cond_parts = [p.strip() for p in re.split(r"\bor\b|/|\|", condition_value, flags=re.IGNORECASE) if p.strip()]
        if any(self._normalize_for_match(part) == query for part in cond_parts):
            return 0.96
        if any(self._normalize_for_match(part) in query for part in cond_parts):
            return 0.9

        overlap = self._token_overlap_score(cond, query)
        fuzzy = SequenceMatcher(None, cond, query).ratio()
        return max(overlap * 0.9, fuzzy * 0.85)

    def _best_matching_edge(self, edges: list[sqlite3.Row], user_text: str) -> sqlite3.Row | None:
        best = None
        best_score = 0.0
        for e in edges:
            cond = str(e["condition_value"] or "").strip()
            if not cond:
                continue
            score = self._edge_match_score(cond, user_text)
            priority_boost = min(0.05, max(0.0, float(e["priority"] or 0) * 0.005))
            score += priority_boost
            if score > best_score:
                best_score = score
                best = e

        if best_score >= 0.35:
            return best
        return None

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
                        is_exact_eligible, is_semantic_eligible, status, source_note, created_by,
                        approval_status, priority
                    )
                    VALUES (?, NULL, ?, ?, ?, ?, ?, 'active', ?, 'json_import', 'approved', ?)
                    """,
                    (
                        category_id,
                        question,
                        normalize_question_text(question),
                        answer,
                        1 if record.get("is_exact_eligible", True) else 0,
                        1 if record.get("is_semantic_eligible", True) else 0,
                        str(record.get("source_note") or "json_import"),
                        int(record.get("priority") or 0),
                    ),
                )
                created += 1

        return created, errors

    def list_qna_pairs(
        self,
        *,
        search: str | None = None,
        category_code: str | None = None,
        status: str | None = None,
        approval_status: str | None = None,
    ) -> list[dict[str, Any]]:
        with self._conn() as conn:
            self._ensure_qna_pair_columns(conn)
            query = """
                SELECT
                    q.id,
                    q.question,
                    q.normalized_question,
                    q.answer,
                    q.is_exact_eligible,
                    q.is_semantic_eligible,
                    q.status,
                    q.approval_status,
                    COALESCE(q.priority, 0) AS priority,
                    q.source_note,
                    q.created_at,
                    q.updated_at,
                    c.code AS category_code
                FROM qna_pairs q
                LEFT JOIN categories c ON c.id = q.category_id
                WHERE 1=1
            """
            params: list[Any] = []
            if status:
                query += " AND q.status=?"
                params.append(status)
            if approval_status:
                query += " AND COALESCE(q.approval_status, 'approved')=?"
                params.append(approval_status)
            if category_code:
                query += " AND c.code=?"
                params.append(category_code)
            if search:
                query += " AND (lower(q.question) LIKE ? OR lower(q.answer) LIKE ? OR lower(COALESCE(q.source_note,'')) LIKE ?)"
                like = f"%{search.strip().lower()}%"
                params.extend([like, like, like])

            query += " ORDER BY COALESCE(q.priority, 0) DESC, q.updated_at DESC, q.id DESC"
            rows = conn.execute(query, params).fetchall()
            return [dict(r) for r in rows]

    def create_qna_pair(
        self,
        *,
        question: str,
        answer: str,
        category_code: str | None,
        source_note: str | None,
        is_exact_eligible: bool,
        is_semantic_eligible: bool,
        approval_status: str,
        priority: int,
    ) -> int:
        normalized_question = normalize_question_text(question)
        with self._conn() as conn:
            self._ensure_qna_pair_columns(conn)
            category_id = None
            if category_code:
                category_id = self._get_or_create_category_id(conn, code=category_code)

            cur = conn.execute(
                """
                INSERT INTO qna_pairs (
                    category_id, source_document_id, question, normalized_question, answer,
                    is_exact_eligible, is_semantic_eligible, status, source_note, created_by,
                    approval_status, priority
                )
                VALUES (?, NULL, ?, ?, ?, ?, ?, 'active', ?, 'admin_ui', ?, ?)
                """,
                (
                    category_id,
                    question,
                    normalized_question,
                    answer,
                    1 if is_exact_eligible else 0,
                    1 if is_semantic_eligible else 0,
                    source_note,
                    approval_status,
                    int(priority),
                ),
            )
            return int(cur.lastrowid)

    def update_qna_pair(self, qna_pair_id: int, payload: dict[str, Any]) -> bool:
        question = str(payload.get("question") or "").strip()
        answer = str(payload.get("answer") or "").strip()
        category_code = normalize_question_text(str(payload.get("category_code") or "")).replace(" ", "_")

        with self._conn() as conn:
            self._ensure_qna_pair_columns(conn)
            category_id = None
            if category_code:
                category_id = self._get_or_create_category_id(conn, code=category_code)

            cur = conn.execute(
                """
                UPDATE qna_pairs
                SET category_id=?,
                    question=?,
                    normalized_question=?,
                    answer=?,
                    is_exact_eligible=?,
                    is_semantic_eligible=?,
                    source_note=?,
                    approval_status=?,
                    priority=?,
                    updated_at=CURRENT_TIMESTAMP
                WHERE id=?
                """,
                (
                    category_id,
                    question,
                    normalize_question_text(question),
                    answer,
                    1 if payload.get("is_exact_eligible", True) else 0,
                    1 if payload.get("is_semantic_eligible", True) else 0,
                    str(payload.get("source_note") or "") or None,
                    str(payload.get("approval_status") or "approved"),
                    int(payload.get("priority") or 0),
                    qna_pair_id,
                ),
            )
            return cur.rowcount > 0

    def archive_qna_pair(self, qna_pair_id: int) -> bool:
        with self._conn() as conn:
            self._ensure_qna_pair_columns(conn)
            cur = conn.execute(
                """
                UPDATE qna_pairs
                SET status='archived', updated_at=CURRENT_TIMESTAMP
                WHERE id=?
                """,
                (qna_pair_id,),
            )
            return cur.rowcount > 0

    def delete_qna_pair(self, qna_pair_id: int) -> bool:
        with self._conn() as conn:
            cur = conn.execute("DELETE FROM qna_pairs WHERE id=?", (qna_pair_id,))
            return cur.rowcount > 0

    def find_qna_exact(self, question: str, normalized_question: str | None = None) -> dict[str, Any] | None:
        nq = normalize_question_text(normalized_question or question)
        q = (question or "").strip().lower()
        with self._conn() as conn:
            self._ensure_qna_pair_columns(conn)
            row = conn.execute(
                """
                SELECT
                    q.*,
                    c.code AS category_code
                FROM qna_pairs q
                LEFT JOIN categories c ON c.id = q.category_id
                WHERE q.status='active'
                  AND COALESCE(q.approval_status, 'approved')='approved'
                  AND q.is_exact_eligible=1
                  AND (
                    q.normalized_question=?
                    OR lower(q.question)=?
                  )
                ORDER BY COALESCE(q.priority, 0) DESC, q.updated_at DESC, q.id DESC
                LIMIT 1
                """,
                (nq, q),
            ).fetchone()
            return dict(row) if row else None

    def find_qna_semantic_candidates(self, question: str, limit: int = 5) -> list[dict[str, Any]]:
        nq = normalize_question_text(question)
        with self._conn() as conn:
            self._ensure_qna_pair_columns(conn)
            rows = conn.execute(
                """
                SELECT q.*, c.code AS category_code
                FROM qna_pairs q
                LEFT JOIN categories c ON c.id = q.category_id
                WHERE q.status='active'
                  AND COALESCE(q.approval_status, 'approved')='approved'
                  AND q.is_semantic_eligible=1
                ORDER BY COALESCE(q.priority, 0) DESC, q.updated_at DESC, q.id DESC
                LIMIT 200
                """
            ).fetchall()

            scored: list[dict[str, Any]] = []
            for row in rows:
                item = dict(row)
                similarity = SequenceMatcher(
                    None,
                    nq,
                    normalize_question_text(item.get("question") or ""),
                ).ratio()
                item["semantic_score"] = float(similarity)
                scored.append(item)

            scored.sort(
                key=lambda x: (float(x.get("semantic_score") or 0.0), int(x.get("priority") or 0), x.get("updated_at") or ""),
                reverse=True,
            )
            return scored[:limit]

    def duplicate_qna_candidates(self, question: str, limit: int = 5) -> list[dict[str, Any]]:
        normalized = normalize_question_text(question)
        candidates = self.find_qna_semantic_candidates(question, limit=limit * 3)
        result: list[dict[str, Any]] = []
        for c in candidates:
            same_normalized = normalize_question_text(c.get("question") or "") == normalized
            similarity = float(c.get("semantic_score") or 0.0)
            if same_normalized or similarity >= 0.86:
                result.append(c)
            if len(result) >= limit:
                break
        return result

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
        session_id: int | None = None,
        message_id: int | None = None,
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
                (session_id, message_id, question, normalized_question, category, answer_text, satisfied, comment, citations_json, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'open')
                """,
                (
                    session_id,
                    message_id,
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

    def create_wrong_answer_report(
        self,
        *,
        session_id: int | None,
        message_id: int | None,
        feedback_id: int | None,
        question: str,
        normalized_question: str | None,
        category: str | None,
        answer_text: str,
        citations: list[dict[str, Any]] | None = None,
        note: str | None = None,
        reason_code: str = "incorrect_answer",
        severity: str = "medium",
    ) -> int:
        if severity not in {"low", "medium", "high"}:
            severity = "medium"
        nq = normalize_question_text(normalized_question or question)
        with self._conn() as conn:
            effective_feedback_id = feedback_id
            if not effective_feedback_id:
                citations_json = json.dumps(citations or [], ensure_ascii=False)
                cur_feedback = conn.execute(
                    """
                    INSERT INTO user_feedback
                    (session_id, message_id, question, normalized_question, category, answer_text, satisfied, comment, citations_json, status)
                    VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?, 'open')
                    """,
                    (
                        session_id,
                        message_id,
                        question,
                        nq,
                        category,
                        answer_text,
                        note,
                        citations_json,
                    ),
                )
                effective_feedback_id = int(cur_feedback.lastrowid)

            cur = conn.execute(
                """
                INSERT INTO wrong_answer_reports
                (session_id, message_id, feedback_id, reason_code, report_text, severity, status)
                VALUES (?, ?, ?, ?, ?, ?, 'open')
                """,
                (session_id, message_id, effective_feedback_id, reason_code, note, severity),
            )
            report_id = int(cur.lastrowid)
            self._insert_audit_log(
                conn,
                action="create_wrong_answer_report",
                entity_type="wrong_answer_reports",
                entity_id=report_id,
                metadata={"reason_code": reason_code, "severity": severity},
            )
            return report_id

    def list_wrong_answer_reports(self, status: str = "open", limit: int = 200) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT
                    wr.id,
                    wr.session_id,
                    wr.message_id,
                    wr.feedback_id,
                    wr.reason_code,
                    wr.report_text,
                    wr.severity,
                    wr.status,
                    wr.assigned_to,
                    wr.admin_action,
                    wr.action_notes,
                    wr.resolved_at,
                    wr.created_at,
                    COALESCE(uf.question, cm.question_text, '') AS question,
                    COALESCE(uf.normalized_question, cm.normalized_question, '') AS normalized_question,
                    uf.category,
                    COALESCE(uf.answer_text, cm.answer_text, '') AS answer_text,
                    COALESCE(uf.citations_json, '[]') AS citations_json
                FROM wrong_answer_reports wr
                LEFT JOIN user_feedback uf ON uf.id = wr.feedback_id
                LEFT JOIN chat_messages cm ON cm.id = wr.message_id
                WHERE (? = '' OR wr.status = ?)
                ORDER BY wr.id DESC
                LIMIT ?
                """,
                (status or "", status or "", max(1, min(limit, 1000))),
            ).fetchall()
        items: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            item["citations"] = json.loads(item.get("citations_json") or "[]")
            items.append(item)
        return items

    def classify_wrong_answer_report(
        self,
        *,
        report_id: int,
        status: str,
        assigned_to: str | None = None,
        reason_code: str | None = None,
        severity: str | None = None,
        action_notes: str | None = None,
    ) -> dict[str, Any]:
        with self._conn() as conn:
            cur = conn.execute(
                """
                UPDATE wrong_answer_reports
                SET status=?,
                    assigned_to=COALESCE(?, assigned_to),
                    reason_code=COALESCE(?, reason_code),
                    severity=COALESCE(?, severity),
                    action_notes=COALESCE(?, action_notes),
                    updated_at=CURRENT_TIMESTAMP
                WHERE id=?
                """,
                (status, assigned_to, reason_code, severity, action_notes, report_id),
            )
            if cur.rowcount <= 0:
                raise ValueError("Wrong-answer report not found")
            audit_id = self._insert_audit_log(
                conn,
                action="classify_wrong_answer_report",
                entity_type="wrong_answer_reports",
                entity_id=report_id,
                metadata={
                    "status": status,
                    "assigned_to": assigned_to,
                    "reason_code": reason_code,
                    "severity": severity,
                },
            )
        return {"report_id": report_id, "audit_log_id": audit_id}

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

    def _insert_audit_log(
        self,
        conn: sqlite3.Connection,
        *,
        action: str,
        entity_type: str,
        entity_id: str | int | None = None,
        metadata: dict[str, Any] | None = None,
        actor_type: str = "admin",
        actor_id: str = "web",
    ) -> int:
        cur = conn.execute(
            """
            INSERT INTO audit_logs (actor_type, actor_id, action, entity_type, entity_id, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                actor_type,
                actor_id,
                action,
                entity_type,
                str(entity_id) if entity_id is not None else None,
                json.dumps(metadata or {}, ensure_ascii=False),
            ),
        )
        return int(cur.lastrowid)

    def log_admin_action(
        self,
        *,
        action: str,
        entity_type: str,
        entity_id: str | int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> int:
        with self._conn() as conn:
            return self._insert_audit_log(
                conn,
                action=action,
                entity_type=entity_type,
                entity_id=entity_id,
                metadata=metadata or {},
                actor_type="admin",
                actor_id="web",
            )

    def create_training_job(
        self,
        *,
        job_type: str,
        params: dict[str, Any] | None = None,
        requested_by: str = "admin:web",
    ) -> int:
        with self._conn() as conn:
            cur = conn.execute(
                """
                INSERT INTO training_jobs (job_type, status, requested_by, started_at, params_json)
                VALUES (?, 'running', ?, CURRENT_TIMESTAMP, ?)
                """,
                (job_type, requested_by, json.dumps(params or {}, ensure_ascii=False)),
            )
            return int(cur.lastrowid)

    def complete_training_job(self, job_id: int, result: dict[str, Any] | None = None) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                UPDATE training_jobs
                SET status='completed',
                    finished_at=CURRENT_TIMESTAMP,
                    result_json=?,
                    updated_at=CURRENT_TIMESTAMP
                WHERE id=?
                """,
                (json.dumps(result or {}, ensure_ascii=False), job_id),
            )

    def fail_training_job(self, job_id: int, error_text: str) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                UPDATE training_jobs
                SET status='failed',
                    finished_at=CURRENT_TIMESTAMP,
                    error_text=?,
                    updated_at=CURRENT_TIMESTAMP
                WHERE id=?
                """,
                (error_text, job_id),
            )

    def list_training_jobs(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT
                    id, job_type, status, requested_by,
                    started_at, finished_at, params_json, result_json, error_text, created_at, updated_at
                FROM training_jobs
                ORDER BY id DESC
                LIMIT ?
                """,
                (max(1, min(limit, 200)),),
            ).fetchall()
        items: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            item["params"] = json.loads(item.get("params_json") or "{}")
            item["result"] = json.loads(item.get("result_json") or "{}")
            items.append(item)
        return items

    def list_audit_logs(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT id, actor_type, actor_id, action, entity_type, entity_id, metadata_json, created_at
                FROM audit_logs
                ORDER BY id DESC
                LIMIT ?
                """,
                (max(1, min(limit, 500)),),
            ).fetchall()
        items: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            item["metadata"] = json.loads(item.get("metadata_json") or "{}")
            items.append(item)
        return items

    def get_train_bot_queue(self, limit: int = 200) -> list[dict[str, Any]]:
        with self._conn() as conn:
            unresolved_rows = conn.execute(
                """
                SELECT
                    id,
                    'unresolved' AS queue_type,
                    question,
                    normalized_question,
                    COALESCE(user_selected_category, category) AS category,
                    answer_text,
                    reason AS detail,
                    status,
                    created_at,
                    (
                      SELECT COUNT(*)
                      FROM unresolved_queries uq2
                      WHERE uq2.normalized_question = uq.normalized_question
                    ) AS repeat_count
                FROM unresolved_queries uq
                WHERE status='open'
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

            wrong_rows: list[sqlite3.Row] = []
            if self._table_exists(conn, "wrong_answer_reports"):
                wrong_rows = conn.execute(
                    """
                    SELECT
                        wr.id,
                        'wrong_answer' AS queue_type,
                        COALESCE(uf.question, cm.question_text, '') AS question,
                        COALESCE(uf.normalized_question, cm.normalized_question, '') AS normalized_question,
                        uf.category AS category,
                        COALESCE(uf.answer_text, cm.answer_text, '') AS answer_text,
                        COALESCE(wr.report_text, wr.reason_code, '') AS detail,
                        wr.status AS status,
                        wr.created_at AS created_at,
                        1 AS repeat_count
                    FROM wrong_answer_reports wr
                    LEFT JOIN user_feedback uf ON uf.id = wr.feedback_id
                    LEFT JOIN chat_messages cm ON cm.id = wr.message_id
                    WHERE wr.status='open'
                    ORDER BY wr.id DESC
                    LIMIT ?
                    """,
                    (limit,),
                ).fetchall()

        items = [dict(r) for r in unresolved_rows] + [dict(r) for r in wrong_rows]
        items.sort(key=lambda x: str(x.get("created_at") or ""), reverse=True)
        for item in items:
            suggestions = ["classify_report", "promote_to_expert", "trigger_category_refresh"]
            if int(item.get("repeat_count") or 1) >= 2:
                suggestions.insert(1, "promote_to_qna")
            if item.get("queue_type") == "wrong_answer":
                suggestions.append("trigger_threshold_refresh")
            item["suggested_actions"] = suggestions
        return items[:limit]

    def promote_unresolved_to_expert(
        self,
        *,
        unresolved_query_id: int,
        category: str,
        expert_answer: str,
        source_note: str | None = None,
    ) -> dict[str, Any]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT question, normalized_question FROM unresolved_queries WHERE id=?",
                (unresolved_query_id,),
            ).fetchone()
            if not row:
                raise ValueError("Unresolved item not found")

        job_id = self.create_training_job(
            job_type="category_refresh",
            params={"workflow": "promote_to_expert", "unresolved_query_id": unresolved_query_id},
        )
        try:
            expert_id = self.save_expert_answer(
                question=str(row["question"] or ""),
                normalized_question=str(row["normalized_question"] or ""),
                category=category,
                expert_answer=expert_answer,
                source_note=source_note,
                unresolved_query_id=unresolved_query_id,
            )
            with self._conn() as conn:
                audit_id = self._insert_audit_log(
                    conn,
                    action="promote_to_expert",
                    entity_type="unresolved_queries",
                    entity_id=unresolved_query_id,
                    metadata={"expert_answer_id": expert_id, "training_job_id": job_id},
                )
            self.complete_training_job(job_id, {"expert_answer_id": expert_id, "audit_log_id": audit_id})
            return {"training_job_id": job_id, "expert_answer_id": expert_id, "audit_log_id": audit_id}
        except Exception as exc:
            self.fail_training_job(job_id, str(exc))
            raise

    def promote_to_qna_pair(
        self,
        *,
        question: str,
        answer: str,
        category_code: str | None = None,
        source_note: str | None = None,
        source_item_type: str,
        source_item_id: int | None = None,
    ) -> dict[str, Any]:
        job_id = self.create_training_job(
            job_type="promote_qna",
            params={
                "workflow": "promote_to_qna",
                "source_item_type": source_item_type,
                "source_item_id": source_item_id,
            },
        )
        try:
            qna_pair_id = self.create_qna_pair(
                question=question,
                answer=answer,
                category_code=category_code,
                source_note=source_note,
                is_exact_eligible=True,
                is_semantic_eligible=True,
                approval_status="approved",
                priority=10,
            )
            with self._conn() as conn:
                audit_id = self._insert_audit_log(
                    conn,
                    action="promote_to_qna",
                    entity_type=source_item_type,
                    entity_id=source_item_id,
                    metadata={"qna_pair_id": qna_pair_id, "training_job_id": job_id},
                )
                if source_item_type == "unresolved_queries" and source_item_id:
                    conn.execute(
                        "UPDATE unresolved_queries SET status='resolved', updated_at=CURRENT_TIMESTAMP WHERE id=?",
                        (source_item_id,),
                    )
            self.complete_training_job(job_id, {"qna_pair_id": qna_pair_id, "audit_log_id": audit_id})
            return {"training_job_id": job_id, "qna_pair_id": qna_pair_id, "audit_log_id": audit_id}
        except Exception as exc:
            self.fail_training_job(job_id, str(exc))
            raise

    def trigger_source_reindex_training(self, data_source_id: int) -> dict[str, Any]:
        job_id = self.create_training_job(
            job_type="reindex",
            params={"workflow": "source_reindex", "data_source_id": data_source_id},
        )
        try:
            ingestion_job_id = self.queue_reingest(data_source_id, trigger_type="train_bot")
            with self._conn() as conn:
                audit_id = self._insert_audit_log(
                    conn,
                    action="trigger_source_reindex",
                    entity_type="data_sources",
                    entity_id=data_source_id,
                    metadata={"ingestion_job_id": ingestion_job_id, "training_job_id": job_id},
                )
            self.complete_training_job(job_id, {"ingestion_job_id": ingestion_job_id, "audit_log_id": audit_id})
            return {"training_job_id": job_id, "ingestion_job_id": ingestion_job_id, "audit_log_id": audit_id}
        except Exception as exc:
            self.fail_training_job(job_id, str(exc))
            raise

    def trigger_category_refresh_training(self, category_code: str | None = None) -> dict[str, Any]:
        job_id = self.create_training_job(
            job_type="category_refresh",
            params={"workflow": "category_refresh", "category_code": category_code},
        )
        with self._conn() as conn:
            metadata = {"category_code": category_code, "status": "completed_noop"}
            audit_id = self._insert_audit_log(
                conn,
                action="trigger_category_refresh",
                entity_type="categories",
                entity_id=category_code,
                metadata=metadata | {"training_job_id": job_id},
            )
        self.complete_training_job(job_id, {"audit_log_id": audit_id, **metadata})
        return {"training_job_id": job_id, "audit_log_id": audit_id, **metadata}

    def trigger_threshold_refresh_training(self) -> dict[str, Any]:
        with self._conn() as conn:
            threshold_config_rows = conn.execute(
                """
                SELECT COUNT(*) AS total
                FROM categories
                WHERE retrieval_scope_json LIKE '%threshold%'
                   OR retrieval_scope_json LIKE '%score%'
                """
            ).fetchone()
            has_config = int(threshold_config_rows["total"] or 0) > 0

        if not has_config:
            return {"ok": False, "message": "No threshold configuration found in category retrieval scopes."}

        job_id = self.create_training_job(
            job_type="threshold_tune",
            params={"workflow": "threshold_refresh"},
        )
        with self._conn() as conn:
            audit_id = self._insert_audit_log(
                conn,
                action="trigger_threshold_refresh",
                entity_type="categories",
                entity_id=None,
                metadata={"training_job_id": job_id, "status": "completed_noop"},
            )
        self.complete_training_job(job_id, {"audit_log_id": audit_id, "status": "completed_noop"})
        return {"ok": True, "training_job_id": job_id, "audit_log_id": audit_id}

    def resolve_wrong_answer_report(
        self,
        *,
        report_id: int,
        admin_action: str,
        action_notes: str | None = None,
        resolution_type: str | None = None,
    ) -> dict[str, Any]:
        with self._conn() as conn:
            cur = conn.execute(
                """
                UPDATE wrong_answer_reports
                SET status='resolved',
                    admin_action=?,
                    action_notes=?,
                    reason_code=COALESCE(?, reason_code),
                    resolved_at=CURRENT_TIMESTAMP,
                    updated_at=CURRENT_TIMESTAMP
                WHERE id=? AND status='open'
                """,
                (admin_action, action_notes, resolution_type, report_id),
            )
            if cur.rowcount <= 0:
                raise ValueError("Wrong-answer report not found or already resolved")
            audit_id = self._insert_audit_log(
                conn,
                action="resolve_wrong_answer_report",
                entity_type="wrong_answer_reports",
                entity_id=report_id,
                metadata={"admin_action": admin_action, "action_notes": action_notes},
            )
        return {"report_id": report_id, "audit_log_id": audit_id}

    def convert_wrong_answer_to_expert(
        self,
        *,
        report_id: int,
        category: str,
        expert_answer: str,
        source_note: str | None = None,
    ) -> dict[str, Any]:
        rows = self.list_wrong_answer_reports(status="", limit=1000)
        report = next((r for r in rows if int(r["id"]) == int(report_id)), None)
        if not report:
            raise ValueError("Wrong-answer report not found")

        job_id = self.create_training_job(
            job_type="category_refresh",
            params={"workflow": "wrong_report_to_expert", "report_id": report_id},
        )
        try:
            expert_answer_id = self.save_expert_answer(
                question=str(report.get("question") or ""),
                normalized_question=str(report.get("normalized_question") or ""),
                category=category,
                expert_answer=expert_answer,
                source_note=source_note,
                unresolved_query_id=None,
            )
            resolved = self.resolve_wrong_answer_report(
                report_id=report_id,
                admin_action="convert_to_expert_answer",
                action_notes=source_note,
                resolution_type="expert_answer",
            )
            self.complete_training_job(job_id, {"expert_answer_id": expert_answer_id, **resolved})
            return {"training_job_id": job_id, "expert_answer_id": expert_answer_id, **resolved}
        except Exception as exc:
            self.fail_training_job(job_id, str(exc))
            raise

    def convert_wrong_answer_to_qna(
        self,
        *,
        report_id: int,
        answer: str,
        category_code: str | None = None,
        source_note: str | None = None,
    ) -> dict[str, Any]:
        rows = self.list_wrong_answer_reports(status="", limit=1000)
        report = next((r for r in rows if int(r["id"]) == int(report_id)), None)
        if not report:
            raise ValueError("Wrong-answer report not found")
        result = self.promote_to_qna_pair(
            source_item_type="wrong_answer_reports",
            source_item_id=report_id,
            question=str(report.get("question") or ""),
            answer=answer,
            category_code=category_code,
            source_note=source_note,
        )
        resolved = self.resolve_wrong_answer_report(
            report_id=report_id,
            admin_action="convert_to_qna_pair",
            action_notes=source_note,
            resolution_type="qna_pair",
        )
        return {**result, **resolved}

    def convert_wrong_answer_to_category_fix(
        self,
        *,
        report_id: int,
        category_code: str | None = None,
        action_notes: str | None = None,
    ) -> dict[str, Any]:
        refresh = self.trigger_category_refresh_training(category_code)
        resolved = self.resolve_wrong_answer_report(
            report_id=report_id,
            admin_action="category_fix",
            action_notes=action_notes,
            resolution_type="category_fix",
        )
        return {**refresh, **resolved}

    def convert_wrong_answer_to_source_issue(
        self,
        *,
        report_id: int,
        data_source_id: int | None = None,
        action_notes: str | None = None,
    ) -> dict[str, Any]:
        result: dict[str, Any]
        if data_source_id:
            result = self.trigger_source_reindex_training(data_source_id)
        else:
            result = {"ok": True, "message": "Source issue logged; no reindex requested"}
        resolved = self.resolve_wrong_answer_report(
            report_id=report_id,
            admin_action="source_issue",
            action_notes=action_notes,
            resolution_type="source_issue",
        )
        return {**result, **resolved}

    def list_chat_sessions(
        self,
        *,
        date_from: str | None = None,
        date_to: str | None = None,
        category_code: str | None = None,
        response_mode: str | None = None,
        feedback_status: str | None = None,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        where: list[str] = ["1=1"]
        params: list[Any] = []
        if date_from:
            where.append("datetime(cs.started_at) >= datetime(?)")
            params.append(date_from)
        if date_to:
            where.append("datetime(cs.started_at) <= datetime(?)")
            params.append(date_to)
        if category_code:
            where.append(
                """
                EXISTS (
                    SELECT 1 FROM chat_messages cm2
                    LEFT JOIN categories c2 ON c2.id = cm2.category_id
                    WHERE cm2.session_id = cs.id
                      AND COALESCE(c2.code, '') = ?
                )
                """
            )
            params.append(category_code)
        if response_mode:
            where.append(
                """
                EXISTS (
                    SELECT 1 FROM chat_messages cm3
                    WHERE cm3.session_id = cs.id
                      AND COALESCE(cm3.answer_mode, '') = ?
                )
                """
            )
            params.append(response_mode)
        if feedback_status == "satisfied":
            where.append(
                "EXISTS (SELECT 1 FROM user_feedback uf WHERE uf.session_id=cs.id AND uf.satisfied=1)"
            )
        elif feedback_status == "unsatisfied":
            where.append(
                "EXISTS (SELECT 1 FROM user_feedback uf WHERE uf.session_id=cs.id AND uf.satisfied=0)"
            )
        elif feedback_status == "none":
            where.append("NOT EXISTS (SELECT 1 FROM user_feedback uf WHERE uf.session_id=cs.id)")

        query = f"""
            SELECT
                cs.id,
                cs.session_key,
                cs.user_key,
                cs.channel,
                cs.status,
                cs.started_at,
                cs.ended_at,
                cs.metadata_json,
                COUNT(cm.id) AS message_count,
                SUM(CASE WHEN cm.answer_text IS NOT NULL AND cm.answer_text <> '' THEN 1 ELSE 0 END) AS answer_count,
                SUM(CASE WHEN uf.id IS NOT NULL THEN 1 ELSE 0 END) AS feedback_count,
                SUM(CASE WHEN uf.satisfied=0 THEN 1 ELSE 0 END) AS unsatisfied_count,
                SUM(CASE WHEN wr.id IS NOT NULL AND wr.status='open' THEN 1 ELSE 0 END) AS wrong_answer_open_count,
                MAX(cm.created_at) AS last_message_at
            FROM chat_sessions cs
            LEFT JOIN chat_messages cm ON cm.session_id = cs.id
            LEFT JOIN user_feedback uf ON uf.message_id = cm.id
            LEFT JOIN wrong_answer_reports wr ON wr.message_id = cm.id
            WHERE {' AND '.join(where)}
            GROUP BY cs.id
            ORDER BY cs.id DESC
            LIMIT ?
        """
        params.append(max(1, min(limit, 1000)))
        with self._conn() as conn:
            rows = conn.execute(query, params).fetchall()
        items: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            item["metadata"] = json.loads(item.get("metadata_json") or "{}")
            item["admin_note"] = str(item["metadata"].get("admin_note") or "")
            items.append(item)
        return items

    def get_chat_session_detail(self, session_id: int) -> dict[str, Any] | None:
        with self._conn() as conn:
            session_row = conn.execute(
                """
                SELECT id, session_key, user_key, channel, status, started_at, ended_at, metadata_json
                FROM chat_sessions
                WHERE id=?
                LIMIT 1
                """,
                (session_id,),
            ).fetchone()
            if not session_row:
                return None

            message_rows = conn.execute(
                """
                SELECT
                    cm.id,
                    cm.session_id,
                    cm.role,
                    cm.question_text,
                    cm.normalized_question,
                    cm.answer_text,
                    cm.answer_mode,
                    COALESCE(c.code, 'unassigned') AS category_code,
                    q.confidence_score AS confidence,
                    cm.evidence_json,
                    cm.created_at
                FROM chat_messages cm
                LEFT JOIN categories c ON c.id = cm.category_id
                LEFT JOIN qna_pairs q ON q.id = cm.qna_pair_id
                WHERE cm.session_id=?
                ORDER BY cm.id ASC
                """,
                (session_id,),
            ).fetchall()

            feedback_rows = conn.execute(
                """
                SELECT id, message_id, satisfied, comment, status, created_at
                FROM user_feedback
                WHERE session_id=?
                ORDER BY id DESC
                """,
                (session_id,),
            ).fetchall()
            feedback_by_message: dict[int, list[dict[str, Any]]] = {}
            for row in feedback_rows:
                r = dict(row)
                feedback_by_message.setdefault(int(r["message_id"] or 0), []).append(r)

            wrong_rows = conn.execute(
                """
                SELECT id, message_id, reason_code, report_text, severity, status, admin_action, action_notes, created_at, resolved_at
                FROM wrong_answer_reports
                WHERE session_id=?
                ORDER BY id DESC
                """,
                (session_id,),
            ).fetchall()
            wrong_by_message: dict[int, list[dict[str, Any]]] = {}
            for row in wrong_rows:
                r = dict(row)
                wrong_by_message.setdefault(int(r["message_id"] or 0), []).append(r)

            citation_rows = conn.execute(
                """
                SELECT
                    mc.message_id,
                    mc.id,
                    mc.page_no,
                    mc.excerpt,
                    mc.score,
                    sd.file_name,
                    sd.doc_key
                FROM message_citations mc
                LEFT JOIN source_documents sd ON sd.id = mc.source_document_id
                WHERE mc.message_id IN (
                    SELECT id FROM chat_messages WHERE session_id=?
                )
                ORDER BY mc.id ASC
                """,
                (session_id,),
            ).fetchall()
            citations_by_message: dict[int, list[dict[str, Any]]] = {}
            for row in citation_rows:
                r = dict(row)
                citations_by_message.setdefault(int(r["message_id"] or 0), []).append(r)

        session = dict(session_row)
        session["metadata"] = json.loads(session.get("metadata_json") or "{}")
        session["admin_note"] = str(session["metadata"].get("admin_note") or "")

        transcript: list[dict[str, Any]] = []
        for row in message_rows:
            item = dict(row)
            evidence = json.loads(item.get("evidence_json") or "[]") if item.get("evidence_json") else []
            parsed_confidence = item.get("confidence")
            if parsed_confidence is None and isinstance(evidence, list) and evidence:
                first = evidence[0] if isinstance(evidence[0], dict) else {}
                parsed_confidence = first.get("score")
            message_id = int(item["id"])
            item["confidence"] = parsed_confidence
            item["evidence"] = evidence
            item["citations"] = citations_by_message.get(message_id, [])
            item["feedback"] = feedback_by_message.get(message_id, [])
            item["wrong_answer_reports"] = wrong_by_message.get(message_id, [])
            transcript.append(item)

        return {
            "session": session,
            "transcript": transcript,
        }

    def update_chat_session_note(self, session_id: int, admin_note: str) -> bool:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT metadata_json FROM chat_sessions WHERE id=? LIMIT 1",
                (session_id,),
            ).fetchone()
            if not row:
                return False
            metadata = json.loads(row["metadata_json"] or "{}")
            metadata["admin_note"] = admin_note
            cur = conn.execute(
                """
                UPDATE chat_sessions
                SET metadata_json=?, updated_at=CURRENT_TIMESTAMP
                WHERE id=?
                """,
                (json.dumps(metadata, ensure_ascii=False), session_id),
            )
            if cur.rowcount > 0:
                self._insert_audit_log(
                    conn,
                    action="update_chat_session_note",
                    entity_type="chat_sessions",
                    entity_id=session_id,
                    metadata={"admin_note": admin_note},
                )
            return cur.rowcount > 0

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

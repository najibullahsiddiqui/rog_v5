from __future__ import annotations

import sqlite3


V2_SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS data_sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_key TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    source_type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'enabled',
    uri TEXT,
    config_json TEXT,
    last_sync_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (status IN ('enabled', 'disabled')),
    CHECK (source_type IN ('pdf_folder', 's3', 'gdrive', 'api', 'manual_upload', 'database'))
);

CREATE TABLE IF NOT EXISTS source_documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    data_source_id INTEGER NOT NULL,
    doc_key TEXT NOT NULL UNIQUE,
    file_name TEXT NOT NULL,
    version TEXT,
    content_hash TEXT,
    chunk_count INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'active',
    metadata_json TEXT,
    ingested_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (data_source_id) REFERENCES data_sources(id)
);

CREATE TABLE IF NOT EXISTS document_chunks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_document_id INTEGER NOT NULL,
    chunk_key TEXT NOT NULL UNIQUE,
    chunk_index INTEGER NOT NULL,
    page_start INTEGER,
    page_end INTEGER,
    token_count INTEGER,
    normalized_text TEXT,
    text TEXT NOT NULL,
    embedding_ref TEXT,
    metadata_json TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (source_document_id) REFERENCES source_documents(id)
);

CREATE TABLE IF NOT EXISTS categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    description TEXT,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS category_synonyms (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category_id INTEGER NOT NULL,
    synonym TEXT NOT NULL,
    normalized_synonym TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(category_id, normalized_synonym),
    FOREIGN KEY (category_id) REFERENCES categories(id)
);

CREATE TABLE IF NOT EXISTS qna_pairs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category_id INTEGER,
    source_document_id INTEGER,
    question TEXT NOT NULL,
    normalized_question TEXT NOT NULL,
    answer TEXT NOT NULL,
    is_exact_eligible INTEGER NOT NULL DEFAULT 1,
    is_semantic_eligible INTEGER NOT NULL DEFAULT 1,
    status TEXT NOT NULL DEFAULT 'active',
    confidence_score REAL,
    source_note TEXT,
    created_by TEXT,
    approved_by TEXT,
    approved_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (category_id) REFERENCES categories(id),
    FOREIGN KEY (source_document_id) REFERENCES source_documents(id)
);


CREATE TABLE IF NOT EXISTS expert_answers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    question TEXT NOT NULL,
    normalized_question TEXT,
    category TEXT NOT NULL,
    expert_answer TEXT NOT NULL,
    source_note TEXT,
    approval_status TEXT NOT NULL DEFAULT 'approved',
    approved_by TEXT,
    approved_at TEXT,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS unresolved_queries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER,
    message_id INTEGER,
    question TEXT NOT NULL,
    normalized_question TEXT,
    category TEXT,
    user_selected_category TEXT,
    answer_text TEXT,
    reason TEXT,
    source TEXT,
    citations_json TEXT,
    status TEXT NOT NULL DEFAULT 'open',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES chat_sessions(id),
    FOREIGN KEY (message_id) REFERENCES chat_messages(id)
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

CREATE TABLE IF NOT EXISTS decision_trees (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tree_key TEXT NOT NULL UNIQUE,
    category_id INTEGER,
    name TEXT NOT NULL,
    version TEXT NOT NULL DEFAULT '1.0.0',
    status TEXT NOT NULL DEFAULT 'draft',
    description TEXT,
    created_by TEXT,
    approved_by TEXT,
    approved_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (category_id) REFERENCES categories(id)
);

CREATE TABLE IF NOT EXISTS decision_tree_nodes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tree_id INTEGER NOT NULL,
    node_key TEXT NOT NULL,
    node_type TEXT NOT NULL,
    prompt_text TEXT,
    answer_text TEXT,
    metadata_json TEXT,
    is_terminal INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(tree_id, node_key),
    FOREIGN KEY (tree_id) REFERENCES decision_trees(id)
);

CREATE TABLE IF NOT EXISTS decision_tree_edges (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tree_id INTEGER NOT NULL,
    from_node_id INTEGER NOT NULL,
    to_node_id INTEGER NOT NULL,
    condition_type TEXT NOT NULL DEFAULT 'option',
    condition_value TEXT,
    priority INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(tree_id, from_node_id, to_node_id, condition_value),
    FOREIGN KEY (tree_id) REFERENCES decision_trees(id),
    FOREIGN KEY (from_node_id) REFERENCES decision_tree_nodes(id),
    FOREIGN KEY (to_node_id) REFERENCES decision_tree_nodes(id)
);

CREATE TABLE IF NOT EXISTS chat_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_key TEXT NOT NULL UNIQUE,
    user_key TEXT,
    channel TEXT NOT NULL DEFAULT 'web',
    status TEXT NOT NULL DEFAULT 'active',
    started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    ended_at TEXT,
    metadata_json TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS chat_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL,
    role TEXT NOT NULL,
    question_text TEXT,
    normalized_question TEXT,
    answer_text TEXT,
    answer_mode TEXT,
    category_id INTEGER,
    qna_pair_id INTEGER,
    expert_answer_id INTEGER,
    decision_tree_id INTEGER,
    grounded INTEGER NOT NULL DEFAULT 0,
    evidence_json TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES chat_sessions(id),
    FOREIGN KEY (category_id) REFERENCES categories(id),
    FOREIGN KEY (qna_pair_id) REFERENCES qna_pairs(id),
    FOREIGN KEY (expert_answer_id) REFERENCES expert_answers(id),
    FOREIGN KEY (decision_tree_id) REFERENCES decision_trees(id)
);

CREATE TABLE IF NOT EXISTS message_citations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id INTEGER NOT NULL,
    source_document_id INTEGER,
    chunk_id INTEGER,
    page_no INTEGER,
    excerpt TEXT,
    score REAL,
    metadata_json TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (message_id) REFERENCES chat_messages(id),
    FOREIGN KEY (source_document_id) REFERENCES source_documents(id),
    FOREIGN KEY (chunk_id) REFERENCES document_chunks(id)
);

CREATE TABLE IF NOT EXISTS user_feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER,
    message_id INTEGER,
    question TEXT NOT NULL,
    normalized_question TEXT,
    category TEXT,
    answer_text TEXT,
    satisfied INTEGER NOT NULL,
    comment TEXT,
    citations_json TEXT,
    status TEXT NOT NULL DEFAULT 'open',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES chat_sessions(id),
    FOREIGN KEY (message_id) REFERENCES chat_messages(id)
);

CREATE TABLE IF NOT EXISTS wrong_answer_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER,
    message_id INTEGER,
    feedback_id INTEGER,
    reason_code TEXT NOT NULL,
    report_text TEXT,
    severity TEXT NOT NULL DEFAULT 'medium',
    status TEXT NOT NULL DEFAULT 'open',
    assigned_to TEXT,
    admin_action TEXT,
    action_notes TEXT,
    resolved_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES chat_sessions(id),
    FOREIGN KEY (message_id) REFERENCES chat_messages(id),
    FOREIGN KEY (feedback_id) REFERENCES user_feedback(id)
);

CREATE TABLE IF NOT EXISTS training_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'queued',
    requested_by TEXT,
    started_at TEXT,
    finished_at TEXT,
    params_json TEXT,
    result_json TEXT,
    error_text TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (job_type IN ('reindex', 'promote_qna', 'category_refresh', 'threshold_tune'))
);

CREATE TABLE IF NOT EXISTS ingestion_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    data_source_id INTEGER,
    status TEXT NOT NULL DEFAULT 'queued',
    trigger_type TEXT NOT NULL DEFAULT 'manual',
    document_count INTEGER NOT NULL DEFAULT 0,
    chunk_count INTEGER NOT NULL DEFAULT 0,
    started_at TEXT,
    finished_at TEXT,
    summary_json TEXT,
    error_text TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (data_source_id) REFERENCES data_sources(id)
);

CREATE TABLE IF NOT EXISTS analytics_daily_aggregates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date_key TEXT NOT NULL UNIQUE,
    total_messages INTEGER NOT NULL DEFAULT 0,
    grounded_answers INTEGER NOT NULL DEFAULT 0,
    unresolved_answers INTEGER NOT NULL DEFAULT 0,
    feedback_total INTEGER NOT NULL DEFAULT 0,
    satisfaction_rate REAL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS audit_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    actor_type TEXT NOT NULL,
    actor_id TEXT,
    action TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id TEXT,
    request_id TEXT,
    metadata_json TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS response_modes (
    mode TEXT PRIMARY KEY,
    description TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS status_catalog (
    entity TEXT NOT NULL,
    status TEXT NOT NULL,
    description TEXT,
    PRIMARY KEY (entity, status)
);

CREATE INDEX IF NOT EXISTS idx_source_documents_source_id ON source_documents(data_source_id);
CREATE INDEX IF NOT EXISTS idx_source_documents_hash ON source_documents(content_hash);
CREATE INDEX IF NOT EXISTS idx_source_documents_status ON source_documents(status);
CREATE INDEX IF NOT EXISTS idx_document_chunks_doc_id ON document_chunks(source_document_id);
CREATE INDEX IF NOT EXISTS idx_document_chunks_doc_chunk_index ON document_chunks(source_document_id, chunk_index);
CREATE INDEX IF NOT EXISTS idx_qna_category ON qna_pairs(category_id);
CREATE INDEX IF NOT EXISTS idx_qna_status ON qna_pairs(status);
CREATE INDEX IF NOT EXISTS idx_qna_normalized_question ON qna_pairs(normalized_question);
CREATE INDEX IF NOT EXISTS idx_expert_category ON expert_answers(category);
CREATE INDEX IF NOT EXISTS idx_decision_trees_category ON decision_trees(category_id);
CREATE INDEX IF NOT EXISTS idx_chat_messages_session ON chat_messages(session_id);
CREATE INDEX IF NOT EXISTS idx_chat_messages_created ON chat_messages(created_at);
CREATE INDEX IF NOT EXISTS idx_chat_messages_answer_mode ON chat_messages(answer_mode);
CREATE INDEX IF NOT EXISTS idx_message_citations_message ON message_citations(message_id);
CREATE INDEX IF NOT EXISTS idx_user_feedback_category ON user_feedback(category);
CREATE INDEX IF NOT EXISTS idx_user_feedback_status ON user_feedback(status);
CREATE INDEX IF NOT EXISTS idx_wrong_answer_reports_status ON wrong_answer_reports(status);
CREATE INDEX IF NOT EXISTS idx_wrong_answer_reports_message_id ON wrong_answer_reports(message_id);
CREATE INDEX IF NOT EXISTS idx_unresolved_status_created ON unresolved_queries(status, created_at);
CREATE INDEX IF NOT EXISTS idx_unresolved_normalized_question ON unresolved_queries(normalized_question);
CREATE INDEX IF NOT EXISTS idx_training_jobs_type_status ON training_jobs(job_type, status);
CREATE INDEX IF NOT EXISTS idx_ingestion_jobs_source_status ON ingestion_jobs(data_source_id, status);
CREATE INDEX IF NOT EXISTS idx_audit_logs_entity ON audit_logs(entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_audit_logs_created ON audit_logs(created_at);
"""


def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(r[1] == column for r in rows)


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    if not _column_exists(conn, table, column):
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def _seed_defaults(conn: sqlite3.Connection) -> None:
    conn.executemany(
        "INSERT OR IGNORE INTO categories(code, name, description) VALUES (?, ?, ?)",
        [
            ("patent", "Patent", "Patent-related FAQs and expert answers"),
            ("trademark", "Trademark", "Trademark-related FAQs and expert answers"),
            ("copyright", "Copyright", "Copyright-related FAQs and expert answers"),
            ("design", "Design", "Design registration and renewal guidance"),
            ("gi", "Geographical Indication", "GI registration and related questions"),
            ("sicld", "SICLD", "Semiconductor layout-design FAQs"),
        ],
    )

    conn.executemany(
        "INSERT OR IGNORE INTO response_modes(mode, description) VALUES (?, ?)",
        [
            ("exact_faq", "Exact question-answer match from approved FAQ"),
            ("near_faq", "Near FAQ match with strong semantic confidence"),
            ("expert_answer", "Answer served from approved expert answer record"),
            ("decision_tree", "Answer resolved via configured decision tree"),
            ("grounded_synthesis", "Synthesized answer grounded in approved documents"),
            ("unresolved", "No approved answer found; requires follow-up"),
        ],
    )

    conn.executemany(
        "INSERT OR IGNORE INTO status_catalog(entity, status, description) VALUES (?, ?, ?)",
        [
            ("data_sources", "enabled", "Source active for ingestion"),
            ("data_sources", "disabled", "Source excluded from ingestion"),
            ("qna_pairs", "active", "Available for serving"),
            ("qna_pairs", "archived", "Hidden from serving"),
            ("expert_answers", "pending", "Awaiting review"),
            ("expert_answers", "approved", "Approved for serving"),
            ("expert_answers", "rejected", "Rejected by reviewer"),
            ("unresolved_queries", "open", "Needs action"),
            ("unresolved_queries", "resolved", "Closed with answer"),
            ("training_jobs", "queued", "Waiting for worker"),
            ("training_jobs", "running", "Currently processing"),
            ("training_jobs", "completed", "Finished successfully"),
            ("training_jobs", "failed", "Job failed"),
            ("ingestion_jobs", "queued", "Waiting to start"),
            ("ingestion_jobs", "running", "In progress"),
            ("ingestion_jobs", "completed", "Finished successfully"),
            ("ingestion_jobs", "failed", "Job failed"),
        ],
    )


def apply_v2_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(V2_SCHEMA_SQL)

    # Backward-compatible extensions for legacy tables.
    _ensure_column(conn, "expert_answers", "approval_status", "TEXT NOT NULL DEFAULT 'approved'")
    _ensure_column(conn, "expert_answers", "approved_by", "TEXT")
    _ensure_column(conn, "expert_answers", "approved_at", "TEXT")

    _ensure_column(conn, "unresolved_queries", "session_id", "INTEGER")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_expert_approval_status ON expert_answers(approval_status)"
    )

    _ensure_column(conn, "unresolved_queries", "message_id", "INTEGER")
    _ensure_column(conn, "unresolved_queries", "source", "TEXT")

    _seed_defaults(conn)

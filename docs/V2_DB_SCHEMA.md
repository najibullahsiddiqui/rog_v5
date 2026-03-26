# V2 Database Schema and Migration Notes

This document describes the enterprise-ready v2 admin schema for document-grounded chatbot operations.

## Migration entrypoints

- SQL migration file: `app/migrations/0001_v2_schema.sql`.
- Auto-apply on `AdminStore` initialization (`app/core/admin_store.py` via `apply_v2_schema`).
- Manual migration helper: `python scripts/run_migrations.py`.

## Core entities

1. `data_sources` — source configuration (`enabled/disabled`, `source_type`).
2. `source_documents` — per-document version/hash/chunk_count tracking.
3. `document_chunks` — normalized chunk-level storage with document FK.
4. `qna_pairs` — curated Q&A with `is_exact_eligible` and `is_semantic_eligible`.
5. `expert_answers` — includes approval lifecycle (`approval_status`, `approved_by`, `approved_at`) and `source_note`.
6. `categories` and `category_synonyms` — category taxonomy and normalization aliases.
7. `decision_trees`, `decision_tree_nodes`, `decision_tree_edges` — explicit flow graph tables.
8. `chat_sessions`, `chat_messages`, `message_citations` — persistent conversation/evidence trail including `answer_mode` and evidence JSON.
9. `user_feedback` and `wrong_answer_reports` — quality loop, linking reports to messages and admin actions.
10. `unresolved_queries` — unresolved tracking with normalized question and status.
11. `training_jobs` — real jobs: `reindex`, `promote_qna`, `category_refresh`, `threshold_tune`.
12. `ingestion_jobs` — ingestion execution + counts + status.
13. `analytics_daily_aggregates` — daily KPI rollups.
14. `audit_logs` — admin/system action log.

## Seeded defaults

- Categories: patent, trademark, copyright, design, gi, sicld.
- Response modes: exact_faq, near_faq, expert_answer, decision_tree, grounded_synthesis, unresolved.
- Status catalog for key entities (sources, qna, expert answers, unresolved, training, ingestion).

## Indexes

Indexes are included for category, status, created_at, FK joins, and normalized question fields to support admin filtering and workflow execution.

# REVIEW NOTES — v2 Chatbot Admin Platform

_Last updated: 2026-03-26 (UTC)_

## 1) Implemented modules (what is in scope)

### A. Core chatbot runtime
- `/api/ask` chatbot endpoint with decision-tree pre-routing, Q&A exact/semantic short-circuiting, expert-answer short-circuiting, and retrieval fallback.
- `/health` and `/health/diagnostics` endpoints for runtime checks and operational counters.
- Strict unresolved handling (`unresolved_query_id`, unresolved logging).

### B. Admin platform modules (UI + API)
1. **Dashboard**
   - KPI cards, unresolved/feedback slices, quick exports.
2. **Analytics**
   - Dedicated analytics page and backend trend breakdowns.
3. **Data Sources**
   - Source CRUD-lite, status toggle, source documents list, reingest trigger.
4. **Convert JSON**
   - Preview + import for `qna_pairs`, `categories`, `decision_trees`, `knowledge_docs`.
5. **Q&A Pairs**
   - Search/filter/list + create/edit/archive/delete + duplicate suggestions.
6. **Categories**
   - Category CRUD + synonym management + category stats + retrieval scope JSON.
7. **Decision Trees**
   - Decision tree CRUD + runtime session execution and edge matching.
8. **Train Bot**
   - Queue consumption (unresolved + wrong-answer reports), promotion/conversion actions, job status, audit table.
9. **Chat History**
   - Session list with filters + full transcript detail (modes, citations/evidence, feedback, wrong-answer flags) + admin notes + export.

### C. Wrong-answer lifecycle
- User can submit wrong-answer reports (`/api/feedback/wrong-answer`) with optional session/message linkage and note.
- Admin can list/classify/resolve/convert reports into:
  - expert answer
  - Q&A pair
  - category fix
  - source issue
- Train Bot consumes wrong-answer reports in queue.

### D. Evaluation harness
- `scripts/run_eval_harness.py` supports repeatable test sets and outputs report JSON + Markdown.
- Baseline set in `app/evals/default_test_set.json` covers:
  - exact FAQ
  - paraphrased FAQ
  - grounded synthesis
  - out-of-scope
  - category-routing
  - decision-tree
- Metrics tracked:
  - exact match success
  - grounded answer success
  - unresolved rate
  - wrong citation rate (heuristic)
  - response mode distribution
  - latency

---

## 2) Database changes and migrations

### Migration source
- Primary migration entrypoint: `scripts/run_migrations.py`.
- Schema definition + column backfills: `app/core/db_migrations.py` (`apply_v2_schema`).

### Major tables introduced/used in v2
- `data_sources`, `source_documents`, `document_chunks`
- `categories`, `category_synonyms`
- `qna_pairs`, `expert_answers`
- `unresolved_queries`, `answer_feedback`, `user_feedback`
- `decision_trees`, `decision_tree_nodes`, `decision_tree_edges`, `tree_runtime_sessions`
- `chat_sessions`, `chat_messages`, `message_citations`
- `wrong_answer_reports`
- `training_jobs`, `ingestion_jobs`
- `audit_logs`, `analytics_daily_aggregates`, catalogs

### Backward-compat ensure logic
- `AdminStore` includes `_ensure_*` guards for older DBs (`data_sources`, `qna_pairs`, `categories`, `decision_trees`) and calls `apply_v2_schema` on init.

### Migration run steps
1. Stop app.
2. Backup `data/admin_review.db`.
3. Run `python scripts/run_migrations.py`.
4. Start app and verify `/health/diagnostics` + admin pages.

---

## 3) New routes/APIs (reviewer map)

## User-facing
- `POST /api/ask`
- `POST /api/feedback`
- `POST /api/feedback/wrong-answer`
- `POST /api/unresolved-category`

## System
- `GET /health`
- `GET /health/diagnostics`
- `GET /pdf/{file_name:path}`

## Admin pages
- `GET /admin`
- `GET /admin/analytics`

## Admin APIs (high level)
- Dashboard/analytics:
  - `GET /api/admin/summary`
  - `GET /api/admin/dashboard-summary`
  - `GET /api/admin/analytics`
- Unresolved/feedback/wrong-answer:
  - `GET /api/admin/unresolved`
  - `GET /api/admin/feedback`
  - `GET /api/admin/wrong-answer-reports`
  - `POST /api/admin/wrong-answer-reports/{id}/classify`
  - `POST /api/admin/wrong-answer-reports/{id}/resolve`
  - `POST /api/admin/wrong-answer-reports/{id}/convert/expert`
  - `POST /api/admin/wrong-answer-reports/{id}/convert/qna`
  - `POST /api/admin/wrong-answer-reports/{id}/convert/category-fix`
  - `POST /api/admin/wrong-answer-reports/{id}/convert/source-issue`
- Chat history:
  - `GET /api/admin/chat-history/sessions`
  - `GET /api/admin/chat-history/sessions/{session_id}`
  - `POST /api/admin/chat-history/sessions/{session_id}/note`
- Train Bot:
  - `GET /api/admin/train-bot/queue`
  - `GET /api/admin/train-bot/jobs`
  - `GET /api/admin/train-bot/audit`
  - `POST /api/admin/train-bot/actions/promote-expert`
  - `POST /api/admin/train-bot/actions/promote-qna`
  - `POST /api/admin/train-bot/actions/source-reindex`
  - `POST /api/admin/train-bot/actions/category-refresh`
  - `POST /api/admin/train-bot/actions/threshold-refresh`
  - `POST /api/admin/train-bot/actions/resolve-wrong-answer`
- Categories:
  - list/create/update/archive/synonyms/stats routes
- Decision Trees:
  - list/get/save/delete routes
- Data Sources:
  - list/create/documents/status/reingest routes
- JSON Convert:
  - preview/import
- Q&A pairs:
  - list/create/update/archive/delete/duplicates
- Expert answer:
  - `POST /api/admin/expert-answer`
- Exports:
  - unresolved, feedback, chat-history exports

---

## 4) Changed files by module

### API / transport
- `app/main.py`
- `app/api/admin_api.py`
- `app/api/user_feedback_api.py`
- `app/api/unresolved_category_api.py`

### Persistence / core
- `app/core/admin_store.py`
- `app/core/db_migrations.py`
- `app/core/retrieval.py`
- `app/core/pipeline.py`

### Services / repositories
- `app/services/categories_service.py`
- `app/services/chat_history_service.py`
- `app/repositories/admin_repository.py` (delegation)

### Schemas
- `app/schemas/admin.py`
- `app/schemas/qna.py`
- `app/schemas/__init__.py`

### Admin UI
- `app/templates/admin_dashboard.html`
- `app/static/admin.js`
- `app/static/admin.css`

### User UI
- `app/static/app.js`
- `app/static/bekarapp.js`

### Tooling / docs
- `scripts/run_migrations.py`
- `scripts/seed_admin_baseline.py`
- `scripts/run_eval_harness.py`
- `app/evals/default_test_set.json`
- `docs/ADMIN_V2_RUNBOOK.md`
- `README.md`

---

## 5) Known gaps, shortcuts, and risks (explicit)

1. **API surface is very large and concentrated in `admin_api.py`**
   - Risk: harder review/testing and inconsistent patterns over time.
   - Suggested next step: split by domain routers (`admin_data_sources_api.py`, `admin_qna_api.py`, etc.).

2. **Audit events are improved but not fully normalized**
   - Different action names exist across layers (store + api).
   - Suggested next step: central event constant catalog and schema contract for `metadata_json`.

3. **Evaluation harness wrong-citation metric is heuristic**
   - Useful for pre-demo spotting, not a full factual verifier.
   - Suggested next step: per-case assertion schema with stricter citation source/page checks.

4. **No comprehensive automated test suite committed**
   - Current state relies heavily on smoke/manual verification + eval harness.
   - Suggested next step: add pytest integration tests for key admin workflows.

5. **Some operations are synchronous and DB-heavy in request path**
   - Risk at higher traffic/admin concurrency.
   - Suggested next step: queue long-running admin operations and add job workers.

6. **Frontend action UX uses prompts in a few train-bot flows**
   - Works for internal demos; not ideal for production operator UX.

---

## 6) Exact local run steps

1. Python 3.11+, create venv and activate.
2. Install dependencies:
   - `pip install -r requirements.txt`
3. Run migrations:
   - `python scripts/run_migrations.py`
4. Optional baseline seed:
   - `python scripts/seed_admin_baseline.py`
5. Put approved PDFs in:
   - `data/source_pdfs/`
6. Build index:
   - `python scripts/ingest_pdfs.py --source data/source_pdfs`
7. Start app:
   - `uvicorn app.main:app --reload`
8. Open:
   - App: `http://127.0.0.1:8000/`
   - Admin: `http://127.0.0.1:8000/admin`

### Optional evaluation run
- `python scripts/run_eval_harness.py --test-set app/evals/default_test_set.json`
- Reports written to: `data/eval_reports/`

---

## 7) Demo flow script (reviewer walkthrough)

### Step 1 — Exact FAQ answer
1. Ask: a direct FAQ-like question with known wording.
2. Show returned answer and citations.
3. Mention expected source mode (e.g., qna exact / grounded retrieval).

### Step 2 — Paraphrased question answer
1. Ask semantically equivalent paraphrase.
2. Show still-correct answer path (semantic/qna/retrieval).

### Step 3 — Grounded synthesis answer
1. Ask a synthesis query requiring combining document evidence.
2. Show citations and explain evidence snippets.

### Step 4 — Wrong answer report
1. In chat UI click **Not satisfied**.
2. Submit optional note.
3. Confirm report created in wrong-answer pipeline.

### Step 5 — Admin correction (Train Bot / Q&A / Expert)
1. Open Admin → Train Bot.
2. Select wrong-answer queue item.
3. Demonstrate one of:
   - Convert to Expert Answer,
   - Convert to Q&A Pair,
   - Category Fix / Source Issue.
4. Show job + audit rows updated.

### Step 6 — Improved follow-up behavior
1. Re-ask same user question.
2. Show improved answer source and reduced unresolved behavior.

### Step 7 — Chat history inspection
1. Open Admin → Chat History.
2. Filter to session and open transcript.
3. Show response mode, citations/evidence, feedback/wrong flags, admin note.

### Step 8 — Analytics view
1. Open Admin → Analytics.
2. Show unresolved/wrong trend and mode distribution charts/tables.
3. Explain whether remediation moved metrics in expected direction.

---

## 8) Reviewer quick-start checklist
- [ ] App boots and `/health` is OK.
- [ ] Admin modules open without placeholders.
- [ ] Wrong-answer report can be filed from user chat.
- [ ] Train Bot action mutates data and writes audit/job rows.
- [ ] Follow-up query shows improved behavior.
- [ ] Chat history and analytics reflect the workflow.
- [ ] Evaluation harness report can be generated and reviewed.


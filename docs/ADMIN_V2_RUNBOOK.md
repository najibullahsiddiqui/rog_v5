# Admin Platform v2 Runbook

## 1) Local setup
1. Create/activate venv.
2. Install dependencies:
   - `pip install -r requirements.txt`
3. Run DB migrations:
   - `python scripts/run_migrations.py`
4. (Optional) seed baseline admin data:
   - `python scripts/seed_admin_baseline.py`
5. Ingest PDFs if needed:
   - `python scripts/ingest_pdfs.py --source data/source_pdfs`
6. Set admin token (required):
   - Linux/macOS: `export ADMIN_TOKEN='change-me-demo-token'`
   - PowerShell: `$env:ADMIN_TOKEN='change-me-demo-token'`
7. Start app:
   - `uvicorn app.main:app --reload`
8. Open admin:
   - `http://127.0.0.1:8000/admin` (redirects to `/admin/login` if not signed in)

## 2) Environment variables
Configured in `app/core/settings.py`.

- `OLLAMA_BASE_URL` (default: `http://localhost:11434`)
- `OLLAMA_MODEL` (default: `qwen2.5:7b-instruct`)
- `EMBEDDING_MODEL` (remote fallback model)
- `RERANKER_MODEL` (remote fallback model)
- `EMBED_MODEL_PATH` (local embedding model path override)
- `RERANKER_MODEL_PATH` (local reranker model path override)
- `TOP_K_VECTOR` (default: `15`)
- `TOP_K_BM25` (default: `15`)
- `TOP_K_RERANK` (default: `8`)
- `MIN_CONTEXT_CHARS` (default: `80`)
- `MIN_RERANK_SCORE` (default: `0.0`)
- `ADMIN_TOKEN` (default: `demo-admin-token`; change for demo/prod)
- `ADMIN_SESSION_COOKIE` (default: `ip_admin_session`)

## 3) Migration steps (safe order)
1. Stop app instances.
2. Backup `data/admin_review.db`.
3. Run `python scripts/run_migrations.py`.
4. Start app and open `/health/diagnostics`.
5. Verify admin modules load and list data.

## 4) Core module boundaries
- `app/api/*`: transport layer (HTTP parsing, status codes, DTO mapping).
- `app/services/*`: orchestration/business use-cases.
- `app/repositories/*`: abstraction around persistence adapters.
- `app/core/admin_store.py`: sqlite persistence and query primitives.
- `app/static/*` + `app/templates/*`: admin/user presentation only.

Keep business logic in services/store, not in templates/static JS.

## 5) Audit expectations
Mutating admin actions should create audit entries in `audit_logs`, especially:
- category CRUD state changes
- qna pair CRUD state changes
- decision-tree save/delete
- data source lifecycle actions
- train-bot conversion actions
- wrong-answer report classification/resolution/conversion

## 6) Evaluation harness
Run:
- `python scripts/run_eval_harness.py --test-set app/evals/default_test_set.json`

Outputs:
- `data/eval_reports/eval_report_<timestamp>.json`
- `data/eval_reports/eval_report_<timestamp>.md`

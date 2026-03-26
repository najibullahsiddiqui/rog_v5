# IP India Strict RAG Bot

A small, strict, document-grounded chatbot for 2-4 approved PDFs.

## What it does
- Answers only from the indexed PDFs
- Shows source document names and page numbers
- Refuses to answer when support is weak
- Uses hybrid retrieval: BM25 + vector search + reranker
- Uses a local LLM through Ollama (`qwen2.5:7b-instruct` by default)

## Recommended local setup
1. Install Python 3.11+
2. Install Ollama and pull the model:
   - `ollama pull qwen2.5:7b-instruct`
3. Create venv and install requirements:
   - `python -m venv .venv`
   - Windows: `.venv\Scripts\activate`
   - `pip install -r requirements.txt`
4. Put approved PDFs inside `data/source_pdfs/`
5. Run ingestion:
   - `python scripts/ingest_pdfs.py --source data/source_pdfs`
6. Start the app:
   - `uvicorn app.main:app --reload`
7. Open:
   - `http://127.0.0.1:8000`
8. Admin access:
   - Set `ADMIN_TOKEN` in env (example: `ADMIN_TOKEN=change-me-demo-token`)
   - Open `http://127.0.0.1:8000/admin` and sign in with that token

## Folder structure
- `app/` - FastAPI app and core logic
- `app/templates/` - UI template
- `app/static/` - CSS and JS
- `data/source_pdfs/` - place approved PDFs here
- `data/index/` - generated indexes and metadata
- `scripts/ingest_pdfs.py` - ingestion script

## Core behavior
- Strict prompt: answer only from provided context
- If answer not found in retrieved context, say so
- Context includes doc name, page number, and excerpt

## Notes
- This version is designed for born-digital PDFs.
- For scanned PDFs, run OCR first, then ingest the OCR output PDFs.
- Keep the corpus small and approved.
- For demos, this is better than open-ended chatbot behavior.

## Useful commands
### Pull model
`ollama pull qwen2.5:7b-instruct`

### Rebuild index
`python scripts/ingest_pdfs.py --source data/source_pdfs --reset`

### Run app
`uvicorn app.main:app --host 0.0.0.0 --port 8000`

### Admin token (required for /admin and /api/admin/*)
Linux/macOS:
`export ADMIN_TOKEN='change-me-demo-token'`

Windows PowerShell:
`$env:ADMIN_TOKEN='change-me-demo-token'`

### Admin v2 runbook
See: `docs/ADMIN_V2_RUNBOOK.md` for setup, env vars, migrations, boundaries, and audit expectations.

### Run evaluation harness
`python scripts/run_eval_harness.py --test-set app/evals/default_test_set.json`

The evaluator writes JSON + Markdown reports to `data/eval_reports/` and prints summary metrics:
- exact match success
- grounded answer success
- unresolved rate
- wrong citation rate
- response mode distribution
- latency (avg/p95/max)

## Recommended demo flow
- Ask direct section-based questions
- Ask page-specific questions
- Ask one out-of-scope question to show refusal behavior

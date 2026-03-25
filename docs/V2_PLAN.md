# IP SaarthiX / IP Assistant – V2 Execution Plan

## 1) Current Architecture Summary (As-Is)

### 1.1 Runtime stack
- **Backend:** FastAPI app (`app/main.py`) with API routes for ask, admin, feedback, unresolved category updates, and PDF file serving.
- **Frontend:** Server-rendered HTML templates + static JS/CSS for chat (`index.html`, `app.js`) and admin (`admin_dashboard.html`, `admin.js`).
- **Storage:**
  - **SQLite** (`data/admin_review.db`) for unresolved queries, user feedback, expert answers.
  - **Index artifacts** in `data/index/` (`faiss.index`, `bm25.pkl`, `chunks.jsonl`).
- **Models:** SentenceTransformer embedding model + CrossEncoder reranker; Ollama model for generation.

### 1.2 Existing backend route map
- `POST /api/ask` – primary answer endpoint with expert-answer short-circuit and retrieval pipeline fallback.
- `POST /api/feedback` – logs user satisfaction feedback.
- `POST /api/unresolved-category` – allows user-selected category for unresolved items.
- `GET /admin` – admin dashboard UI.
- `GET /api/admin/summary` – KPI summary.
- `GET /api/admin/unresolved` – unresolved list.
- `GET /api/admin/feedback` – feedback list.
- `POST /api/admin/expert-answer` – save curated expert answer and optionally resolve unresolved query.
- `GET /api/admin/export/unresolved` – unresolved Excel export.
- `GET /api/admin/export/feedback` – feedback Excel export.
- `GET /pdf/{file_name}` – inline PDF viewer for citations.

### 1.3 Ingestion pipeline (current)
- `scripts/ingest_pdfs.py` runs `run_ingestion`.
- `app/core/ingestion.py`:
  1. Parses PDFs with PyMuPDF.
  2. Heuristically detects FAQ-like docs.
  3. Extracts Q/A pairs using state machine, else paragraph chunk fallback.
  4. Builds chunk records with page span metadata.
  5. Creates FAISS vector index + BM25 index.
  6. Writes artifacts to `data/index/`.

### 1.4 Answer pipeline (current)
Order of answer modes in `POST /api/ask`:
1. **Curated expert exact match** via `AdminStore.find_expert_answer` (normalized exact question match).
2. Else run `QAPipeline.ask(question)`:
   - Retriever fast-path direct Q similarity match (`DIRECT_MATCH_THRESHOLD=0.80`), else hybrid retrieval + rerank.
   - Pipeline performs a second direct-match pass over hits.
   - If near-exact FAQ match found: return extracted chunk answer (`faq_exact`).
   - Else synthesize via LLM from retrieved context (`pdf_synthesized`).
   - If unsupported/no answer: refusal text.
3. If refusal: unresolved query is logged in DB.

### 1.5 Admin module (current)
- Overview with KPI cards.
- Unresolved and feedback table views with category chips + search.
- Expert answer modal (curated answer creation).
- Excel exports for unresolved/feedback.

---

## 2) Salvageable vs Replace/Refactor

## 2.1 Strong salvageable components
1. **Strict refusal pattern and grounded citations**: already implemented and aligned to “approved docs only” objective.
2. **Ingestion/indexing baseline**: FAQ extraction + fallback chunking + FAISS/BM25 is useful and production-adaptable.
3. **Core admin persistence** (`unresolved_queries`, `answer_feedback`, `expert_answers`) is a strong seed for review workflows.
4. **Expert-first answering path** is directly aligned to curated override behavior.
5. **Category inference helpers** can be reused as fallback tagging.

## 2.2 Components to refactor (not discard)
1. **Direct match quality gate**: current fuzzy threshold may produce false positives for “direct approved answer” mode.
2. **Single-table admin UX**: not modularized to competitor-level features (analytics, data sources, decision trees, train bot, chat history).
3. **Answer provenance schema**: response metadata exists but no explicit, auditable “mode contract” for compliance reporting.
4. **Data model fragmentation**: no structured entities for data sources, Q&A pairs, categories taxonomy versioning, decision trees, training jobs.
5. **No real “train bot” workflow**: ingestion is script-based; admin-triggerable jobs/status/progress absent.

## 2.3 Replace/rebuild candidates
1. **Admin IA (information architecture)** to module-first navigation.
2. **Route organization** to versioned `/api/v2/*` endpoints with explicit domain grouping.
3. **Observability and analytics layer** (currently only summary counts).
4. **Chat history persistence** (currently not first-class).

---

## 3) Gap Analysis vs Competitor Modules

Required competitor modules:
- Dashboard ✅ (partial)
- Analytics ❌ (minimal only)
- Data Sources ❌
- Convert JSON ❌
- Q&A Pairs ⚠️ (implicit via chunks + expert answers, not managed as first-class)
- Categories ⚠️ (limited enum-like behavior, no lifecycle)
- Decision Trees ❌
- Train Bot ❌ (no real admin workflow)
- Chat History ❌ (no structured persisted conversation model)

### Critical product gaps
1. **No explicit governance layer for approved document set** (source lifecycle, publish states, checksums, versioning).
2. **No structured curated Q&A repository** separate from extraction chunks and expert answers.
3. **No deterministic answer-mode hierarchy contract with audit log for each response.**
4. **No conversation/session storage for auditing or analytics.**
5. **No operational job system for ingest/reindex/rebuild with statuses.**

---

## 4) Proposed V2 Module Map

## 4.1 Modules (user-facing/admin)
1. **Dashboard**
   - KPI cards (requests, resolution rate, unresolved backlog, feedback satisfaction, source coverage).
   - Recent operational events (ingestion jobs, publish events, failures).

2. **Analytics**
   - Query volume trends, refusal rate, top unanswered intents.
   - Answer-mode distribution (direct_approved, curated_expert, grounded_synthesized, refusal).
   - Category-level quality metrics.

3. **Data Sources**
   - Manage approved documents (upload/register, version, status, checksum, active/inactive).
   - Source processing status (parsed/indexed/published).

4. **Convert JSON**
   - Deterministic conversion workflow from source docs/QA CSV/Excel into canonical JSON schemas.
   - Validation + preview + import report.
   - Must be a real conversion + persistence workflow (no placeholder page).

5. **Q&A Pairs**
   - Canonical curated QA store with statuses (draft/reviewed/published/archived).
   - Exact-match answer source with highest precedence.
   - Bulk import/export.

6. **Categories**
   - Manage taxonomy and aliases.
   - Map data sources and Q&A pairs to categories.
   - Category versioning to avoid breaking analytics.

7. **Decision Trees**
   - Rule-based guided resolution flows (if/then question paths).
   - Explicitly linked to approved outcomes or citations.
   - Optional pre-answer clarifier mode when confidence is low.

8. **Train Bot**
   - Real workflow: “Build/Publish Retrieval Artifacts” job.
   - Tracks source snapshot, chunk stats, index build status, errors, publish timestamp.
   - Rollback to previous published index snapshot.

9. **Chat History**
   - Persist sessions/messages/answer metadata.
   - Admin search and replay with citations + answer mode.

---

## 5) V2 Data Model Plan

> Keep SQLite initially for speed; design tables to be migration-ready to Postgres.

## 5.1 Core governance tables
- `approved_sources`
  - `id`, `name`, `source_type` (pdf/json/qa_import), `checksum`, `version`, `status` (draft/published/archived), `uploaded_at`, `published_at`, `metadata_json`.
- `source_documents`
  - per file/page stats, parse status, extraction warnings.
- `ingestion_jobs`
  - `id`, `job_type`, `requested_by`, `status`, `started_at`, `ended_at`, `log_json`, `artifact_version`.
- `index_snapshots`
  - immutable retrieval artifact versions + active pointer.

## 5.2 Knowledge tables
- `qa_pairs`
  - `id`, `question`, `normalized_question`, `answer`, `category_id`, `source_id`, `status`, `priority`, `effective_from`, `effective_to`.
- `expert_answers`
  - retain existing; add status/version linkage and optional `qa_pair_id`.
- `decision_trees`
  - tree metadata (`id`, `name`, `category_id`, `status`, `version`).
- `decision_tree_nodes`
  - node type (question/condition/outcome), text, next pointers.
- `categories`
  - canonical category records.
- `category_aliases`
  - many aliases to canonical category.

## 5.3 Conversation & analytics tables
- `chat_sessions`
  - `id`, `channel`, `user_hash`, `started_at`, `ended_at`.
- `chat_messages`
  - session message stream with role/content/timestamps.
- `answer_events`
  - one row per assistant answer with:
  - `mode`, `matched_qa_pair_id`, `expert_answer_id`, `index_snapshot_id`, `grounded`, `refusal_reason`, `latency_ms`, `citations_json`.
- `feedback_events`
  - evolve current `answer_feedback` into event style with foreign key to `answer_events`.
- `unresolved_events`
  - unresolved lifecycle state machine (open/triaged/resolved/rejected).

---

## 6) Route Map Proposal (`/api/v2`)

## 6.1 Answering + chat
- `POST /api/v2/chat/sessions` – create session.
- `POST /api/v2/chat/sessions/{id}/messages` – ask question and get answer.
- `GET /api/v2/chat/sessions/{id}` – retrieve transcript.
- `GET /api/v2/chat/history` – admin search/filter.

## 6.2 Knowledge management
- `GET/POST /api/v2/qa-pairs`
- `PUT /api/v2/qa-pairs/{id}`
- `POST /api/v2/qa-pairs/import`
- `GET /api/v2/qa-pairs/export`

- `GET/POST /api/v2/expert-answers`
- `PUT /api/v2/expert-answers/{id}`

## 6.3 Sources + training
- `GET/POST /api/v2/data-sources`
- `POST /api/v2/data-sources/{id}/publish`
- `POST /api/v2/convert/json` (validate + transform + preview)

- `POST /api/v2/train/jobs` (real build trigger)
- `GET /api/v2/train/jobs/{id}`
- `POST /api/v2/train/jobs/{id}/publish`
- `POST /api/v2/train/jobs/{id}/rollback`

## 6.4 Taxonomy + decision trees
- `GET/POST /api/v2/categories`
- `PUT /api/v2/categories/{id}`
- `GET/POST /api/v2/decision-trees`
- `PUT /api/v2/decision-trees/{id}`
- `POST /api/v2/decision-trees/{id}/simulate`

## 6.5 Analytics
- `GET /api/v2/analytics/overview`
- `GET /api/v2/analytics/queries`
- `GET /api/v2/analytics/unresolved`
- `GET /api/v2/analytics/answer-modes`

---

## 7) V2 Answer Pipeline Modes (Strict Compliance Contract)

Non-negotiable order:

1. **Mode A: Approved Direct Match (`direct_approved`)**
   - Match only against **published curated QA pairs** (exact normalized match; optional deterministic alias expansion).
   - Return approved answer verbatim.

2. **Mode B: Curated Expert (`curated_expert`)**
   - If no Mode A match, check published expert answers (exact normalized match).
   - Return expert answer verbatim.

3. **Mode C: Grounded Synthesized (`grounded_synthesized`)**
   - Retrieve from published approved sources only (active snapshot).
   - Synthesize answer only from retrieved evidence.
   - Must return citations and evidence trace.

4. **Mode D: Refusal (`refusal`)**
   - If evidence is weak/insufficient, return refusal text.
   - Log unresolved event for triage.

### Required per-answer audit payload
- `mode`
- `matched_entity_id` (qa_pair/expert)
- `index_snapshot_id`
- `retrieval_scores`
- `citations`
- `refusal_reason` (if any)

This makes the system explainable and enforceably “approved-doc only.”

---

## 8) Phased Implementation Strategy (Recommended Order)

## Phase 0 – Planning hardening (current phase)
- Finalize this v2 plan and schema contract.
- Define answer-mode acceptance tests.

## Phase 1 – Data foundation + migrations
- Add v2 tables (`approved_sources`, `qa_pairs`, `chat_sessions`, `chat_messages`, `answer_events`, `ingestion_jobs`, `index_snapshots`, `categories`, aliases).
- Keep existing tables for backward compatibility; add migration scripts.

## Phase 2 – Strict answer orchestration
- Implement `AnswerOrchestratorV2` with explicit modes A→D.
- Route `POST /api/v2/chat/sessions/{id}/messages` to orchestrator.
- Persist `answer_events` for every response.

## Phase 3 – Data Sources + Train Bot (real workflows)
- Build source management APIs/UI.
- Build ingestion job queue/executor with status tracking.
- Build index snapshot publish/rollback.

## Phase 4 – Q&A Pairs + Convert JSON + Categories
- Add CRUD/import/export for curated Q&A.
- Add deterministic JSON conversion/validation pipeline.
- Add category taxonomy management and mappings.

## Phase 5 – Decision Trees + Chat History
- Decision tree CRUD + runtime resolver for guided disambiguation.
- Full chat history UI/search with transcript replay and answer mode filters.

## Phase 6 – Analytics
- Build analytics endpoints + dashboard charts from `answer_events`, `feedback_events`, unresolved lifecycle.
- Add quality monitoring thresholds and alerts.

## Phase 7 – Cutover and cleanup
- Migrate primary UI to v2 modules.
- Keep `/api/ask` compatibility shim temporarily, then sunset.
- Deprecate obsolete scripts/routes after stable rollout.

---

## 9) Major Risks and Mitigations

1. **False positives in “direct match”**
   - **Risk:** wrong approved answer served.
   - **Mitigation:** exact normalized match for curated QA/expert; no fuzzy direct mode for curated responses.

2. **Source governance drift**
   - **Risk:** unpublished or stale docs influence answers.
   - **Mitigation:** enforce active index snapshot + source publish states.

3. **Admin complexity creep**
   - **Risk:** “fake workflow” screens.
   - **Mitigation:** each UI action must map to a persisted backend job/event.

4. **Migration regressions**
   - **Risk:** old flows break during schema evolution.
   - **Mitigation:** compatibility layer + phased route migration + migration tests.

5. **Operational load (embedding/rerank latency)**
   - **Risk:** slow responses during rebuild or high traffic.
   - **Mitigation:** snapshot build off-path, cache hot queries, measure per-mode latency.

6. **Compliance/audit gaps**
   - **Risk:** cannot prove answer source mode.
   - **Mitigation:** mandatory `answer_events` logging with mode + evidence trace.

---

## 10) Concrete Next Implementation Sprint (first build sprint)

1. Add DB migrations and v2 tables (foundation only).
2. Implement `AnswerOrchestratorV2` with strict mode hierarchy.
3. Add new chat session + message endpoints and persist answer events.
4. Add minimal v2 admin page stubs wired to real APIs for:
   - Data Sources list/create
   - Train jobs list/create/status
   - Q&A Pairs list/create
5. Add smoke tests for strict mode order and refusal behavior.

This order delivers immediate product differentiation while preserving current working flows and minimizing risky refactors.

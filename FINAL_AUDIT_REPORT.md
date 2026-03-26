# FINAL AUDIT REPORT

Date: 2026-03-26 (UTC)
Repository: `rog_v5`
Auditor mode: blunt, evidence-first

## Scope and method
- Reviewed architecture and runtime entrypoints (`app/main.py`, `app/api/admin_api.py`, `app/core/admin_store.py`, `app/core/db_migrations.py`, `scripts/run_eval_harness.py`, `REVIEW_NOTES.md`).
- Ran lightweight executable checks available in this environment.
- Classified every major claim into:
  1. **Verified by code inspection**
  2. **Verified by runtime command output**
  3. **Unverified / not proven in this run**

---

## Executive verdict (blunt)
The codebase is feature-rich but operationally under-protected. The biggest production risk is that **admin and training endpoints are exposed with no authentication/authorization controls in API layer code**. Error handling in `/api/ask` also leaks internal exception text to clients. The system appears functionally broad, but reliability and security claims are ahead of runtime proof in this environment.

---

## Findings

### 1) Critical: admin/API surface is unauthenticated
**Severity:** Critical  
**Status:** Verified by code inspection

**Evidence (code):**
- `app/main.py` mounts `admin_router`, `feedback_router`, and `unresolved_category_router` globally without any auth gate or dependency wrapper.
- `app/api/admin_api.py` defines `/admin` and many `/api/admin/*` mutation endpoints directly (`POST .../convert/*`, `POST .../train-bot/actions/*`, CRUD flows) with no auth dependency.
- A search for authentication hooks (`Depends(...)` auth deps, bearer token handling, login/password checks) returns no meaningful API auth implementation in `app/api` or `app/main.py`.

**Impact:** anyone with network access to the app can potentially operate admin workflows and data mutation endpoints.

**Recommendation:** add mandatory authn/authz middleware/dependencies before any admin route exposure; enforce role checks per endpoint.

---

### 2) High: internal exception details are returned to clients
**Severity:** High  
**Status:** Verified by code inspection

**Evidence (code):**
- In `app/main.py` `/api/ask`, broad `except Exception as exc` returns `{"error": f"Internal error: {exc}"}` to client.

**Impact:** server internals and error strings can leak to end users, increasing information disclosure risk and attack surface reconnaissance.

**Recommendation:** return generic client-safe error messages; keep detailed stack/error text only in server logs.

---

### 3) High: migration script execution path is brittle
**Severity:** High  
**Status:** Verified by runtime command output

**Evidence (runtime):**
- `python scripts/run_migrations.py` fails with `ModuleNotFoundError: No module named 'app'` when invoked as documented without environment prep.
- `PYTHONPATH=. python scripts/run_migrations.py` progresses further but fails due missing dependency `requests` (environment package gap).

**Impact:** onboarding and ops scripts are sensitive to invocation context; docs may be insufficiently explicit about environment setup before migration execution.

**Recommendation:** either
- package/app-install approach (`pip install -e .`) and entrypoint scripts, or
- make scripts path-robust, and update runbook with explicit `PYTHONPATH`/venv prerequisites.

---

### 4) Medium: runtime quality claims exceed current runtime proof
**Severity:** Medium  
**Status:** Unverified in this run

**What is unverified right now:**
- End-to-end ingestion + retrieval + reranker quality behavior
- Admin UI workflow correctness under realistic data
- Evaluation harness metric validity against real corpus and model runtime
- Concurrency and performance characteristics under load

**Reason:** environment lacked installed dependencies/models for full-system boot and endpoint exercise.

**Recommendation:** run a reproducible CI smoke pack (migrations, seed, app startup, API contract checks, and minimal eval harness) and publish pass/fail artifacts.

---

## Verified-by-status matrix

## A) Verified by code inspection
- Admin/API route breadth exists as documented in review notes (large endpoint surface in `admin_api.py`).
- Global router inclusion exists in app bootstrap.
- `/api/ask` has multi-branch logic (decision tree, qna exact/semantic, expert, retrieval fallback, unresolved logging).
- Internal exception text leak behavior exists in `/api/ask`.

## B) Verified by runtime command output
- Static compile check passed for source files via `python -m compileall app scripts`.
- Migration script invocation failed without module path setup (`ModuleNotFoundError: app`).
- Migration script invocation still blocked later by missing packages (`ModuleNotFoundError: requests`) in current environment.

## C) Unverified / not proven in this run
- Full app startup (`uvicorn`) and live endpoint behavior.
- DB migration completion success path in a fully prepared virtualenv.
- Functional correctness of admin actions against realistic datasets.
- Evaluation-harness reported metrics and their stability over repeated runs.

---

## Commands executed (audit trail)
1. `rg --files -g 'AGENTS.md'`
2. `find . -maxdepth 2 -type f | sed 's#^./##' | head -n 200`
3. `sed -n '1,220p' README.md`
4. `sed -n '1,260p' app/main.py`
5. `sed -n '1,260p' REVIEW_NOTES.md`
6. `wc -l app/api/admin_api.py app/core/admin_store.py app/core/db_migrations.py app/core/pipeline.py scripts/run_eval_harness.py app/static/admin.js app/templates/admin_dashboard.html`
7. `rg -n "TODO|FIXME|HACK|pass #|NotImplemented|raise NotImplemented" app scripts docs | head -n 120`
8. `cat requirements.txt`
9. `git status --short`
10. `sed -n '1,240p' app/api/admin_api.py`
11. `sed -n '240,520p' app/main.py`
12. `sed -n '1,260p' app/api/user_feedback_api.py && sed -n '1,220p' app/api/unresolved_category_api.py`
13. `python -m compileall app scripts` (pass)
14. `python scripts/run_migrations.py` (fail: module import path)
15. `PYTHONPATH=. python scripts/run_migrations.py` (fail: missing dependency)

---

## Bottom line
This repository is **feature-complete enough for internal iteration**, but **not production-safe yet** without hard authn/authz on admin surfaces and safer error exposure policy. Runtime claims should be treated as provisional until the full smoke/eval pipeline runs in a dependency-complete environment.

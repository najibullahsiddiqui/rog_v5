from __future__ import annotations

import json
import logging
from pathlib import Path

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.core.schemas import AskRequest
from app.core.pipeline import QAPipeline
from app.core.text_utils import normalize_question_text
from app.core.config import PDF_DIR, INDEX_DIR, ADMIN_SESSION_COOKIE
from app.core.admin_auth import is_admin_authorized, is_valid_admin_token, session_cookie_value
from app.core.admin_store import AdminStore
from app.services.categories_service import CategoriesService

from app.api.admin_api import router as admin_router
from app.api.user_feedback_api import router as feedback_router
from app.api.unresolved_category_api import router as unresolved_category_router


app = FastAPI(title="IP India Strict RAG Bot")

app.include_router(admin_router)
app.include_router(feedback_router)
app.include_router(unresolved_category_router)

store = AdminStore()
categories_service = CategoriesService(store)
REFUSAL_TEXT = "The answer is not available in the approved document set."

BASE_DIR = Path(__file__).resolve().parent
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

pipeline: QAPipeline | None = None
logger = logging.getLogger(__name__)


def get_pipeline() -> QAPipeline:
    global pipeline
    if pipeline is None:
        pipeline = QAPipeline()
    return pipeline


def _is_admin_protected_path(path: str) -> bool:
    return path == "/admin" or path.startswith("/admin/") or path.startswith("/api/admin/")


@app.middleware("http")
async def admin_auth_middleware(request: Request, call_next):
    path = request.url.path
    if not _is_admin_protected_path(path):
        return await call_next(request)

    if path.startswith("/admin/login"):
        return await call_next(request)

    if is_admin_authorized(request):
        return await call_next(request)

    if path.startswith("/api/admin/"):
        return JSONResponse(status_code=401, content={"error": "Unauthorized admin access."})

    return RedirectResponse(url="/admin/login", status_code=302)


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/admin/login", response_class=HTMLResponse)
def admin_login_page(request: Request):
    return templates.TemplateResponse("admin_login.html", {"request": request, "error": None})


@app.post("/admin/login", response_class=HTMLResponse)
async def admin_login(request: Request):
    form = await request.form()
    token = (form.get("token") or "").strip()
    if not is_valid_admin_token(token):
        return templates.TemplateResponse(
            "admin_login.html",
            {"request": request, "error": "Invalid admin token."},
            status_code=401,
        )

    response = RedirectResponse(url="/admin", status_code=302)
    response.set_cookie(
        key=ADMIN_SESSION_COOKIE,
        value=session_cookie_value(),
        httponly=True,
        samesite="lax",
    )
    return response


@app.post("/admin/logout")
def admin_logout():
    response = RedirectResponse(url="/admin/login", status_code=302)
    response.delete_cookie(ADMIN_SESSION_COOKIE)
    return response


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/health/diagnostics")
def health_diagnostics():
    pdf_files = sorted(PDF_DIR.glob("*.pdf"))
    chunk_path = INDEX_DIR / "chunks.jsonl"
    index_path = INDEX_DIR / "faiss.index"
    bm25_path = INDEX_DIR / "bm25.pkl"

    chunk_count = 0
    if chunk_path.exists():
        with chunk_path.open("r", encoding="utf-8") as f:
            chunk_count = sum(1 for line in f if line.strip())

    sample_chunk = None
    if chunk_path.exists():
        with chunk_path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    sample_chunk = json.loads(line)
                    break

    dashboard_totals = store.dashboard_summary().get("totals", {})

    return {
        "ok": True,
        "documents": {
            "pdf_count": len(pdf_files),
            "pdf_files": [p.name for p in pdf_files],
        },
        "index": {
            "faiss_index_exists": index_path.exists(),
            "bm25_exists": bm25_path.exists(),
            "chunks_exists": chunk_path.exists(),
            "chunks_count": chunk_count,
            "sample_chunk": {
                "doc": sample_chunk.get("doc"),
                "page": sample_chunk.get("page"),
            }
            if sample_chunk
            else None,
        },
        "admin": {
            "open_unresolved": dashboard_totals.get("open_unresolved", 0),
            "feedback_total": dashboard_totals.get("feedback_total", 0),
            "expert_answers_total": dashboard_totals.get("expert_answers_total", 0),
        },
    }


@app.get("/pdf/{file_name:path}")
def open_pdf(file_name: str):
    pdf_path = (PDF_DIR / file_name).resolve()
    pdf_root = PDF_DIR.resolve()

    if not str(pdf_path).startswith(str(pdf_root)):
        raise HTTPException(status_code=400, detail="Invalid file path.")

    if not pdf_path.exists() or not pdf_path.is_file():
        raise HTTPException(status_code=404, detail="PDF not found.")

    return FileResponse(
        path=str(pdf_path),
        media_type="application/pdf",
        headers={"Content-Disposition": "inline"},
    )


@app.post("/api/ask")
def ask(payload: AskRequest):
    question = payload.question.strip()
    session_key = (payload.session_key or "").strip() or "default_session"
    if not question:
        return JSONResponse(
            status_code=400,
            content={"error": "Question is required."},
        )

    normalized_question = normalize_question_text(question)

    try:
        def _record_and_return(result_payload: dict) -> dict:
            try:
                store.log_chat_interaction(
                    session_key=session_key,
                    question=question,
                    normalized_question=normalized_question,
                    answer=result_payload.get("answer"),
                    answer_mode=result_payload.get("answer_source"),
                    category_code=result_payload.get("category") or result_payload.get("predicted_category"),
                    grounded=bool(result_payload.get("grounded")),
                    confidence=result_payload.get("confidence"),
                    citations=result_payload.get("citations"),
                )
            except Exception:
                logger.exception("Failed to persist chat interaction.")
            return result_payload

        tree_result = store.run_decision_tree(session_key, question)
        if tree_result:
            if tree_result.get("type") == "prompt":
                return _record_and_return({
                    "answer": tree_result.get("prompt") or "Please choose an option.",
                    "grounded": True,
                    "citations": [],
                    "category": None,
                    "predicted_category": None,
                    "unresolved_query_id": None,
                    "answer_source": "decision_tree_prompt",
                    "debug": {"decision_tree": tree_result},
                })

            if tree_result.get("type") == "terminal":
                outcome_type = tree_result.get("outcome_type")
                if outcome_type == "final_answer":
                    return _record_and_return({
                        "answer": tree_result.get("answer_text") or "Done.",
                        "grounded": True,
                        "citations": [],
                        "category": None,
                        "predicted_category": None,
                        "unresolved_query_id": None,
                        "answer_source": "decision_tree_final",
                        "debug": {"decision_tree": tree_result},
                    })
                if outcome_type == "route_category":
                    routed_category = categories_service.normalize(str(tree_result.get("outcome_value") or ""))
                    result = get_pipeline().ask(question, category_hint_override=routed_category)
                    result["answer_source"] = "decision_tree_route_category"
                    result["debug"] = {**(result.get("debug") or {}), "decision_tree": tree_result}
                    return _record_and_return(result)
                if outcome_type == "route_qna":
                    qna = store.find_qna_exact(str(tree_result.get("outcome_value") or question))
                    if qna:
                        return _record_and_return({
                            "answer": qna["answer"],
                            "grounded": True,
                            "citations": [],
                            "category": qna.get("category_code"),
                            "predicted_category": qna.get("category_code"),
                            "unresolved_query_id": None,
                            "answer_source": "decision_tree_route_qna",
                            "debug": {"decision_tree": tree_result, "qna_pair_id": qna["id"]},
                        })
                if outcome_type == "route_retrieval":
                    routed_category = categories_service.normalize(str(tree_result.get("outcome_value") or ""))
                    result = get_pipeline().ask(question, category_hint_override=routed_category)
                    result["answer_source"] = "decision_tree_route_retrieval"
                    result["debug"] = {**(result.get("debug") or {}), "decision_tree": tree_result}
                    return _record_and_return(result)

        qna_exact = store.find_qna_exact(
            question=question,
            normalized_question=normalized_question,
        )
        if qna_exact:
            return _record_and_return({
                "answer": qna_exact["answer"],
                "grounded": True,
                "citations": [],
                "category": qna_exact.get("category_code"),
                "predicted_category": qna_exact.get("category_code"),
                "unresolved_query_id": None,
                "answer_source": "qna_exact",
                "debug": {
                    "served_from": "qna_pair_exact",
                    "qna_pair_id": qna_exact["id"],
                    "query_info": {
                        "normalized_question": normalized_question,
                    },
                },
            })

        qna_candidates = store.find_qna_semantic_candidates(question, limit=3)
        if qna_candidates and float(qna_candidates[0].get("semantic_score") or 0.0) >= 0.9:
            winner = qna_candidates[0]
            return _record_and_return({
                "answer": winner["answer"],
                "grounded": True,
                "citations": [],
                "category": winner.get("category_code"),
                "predicted_category": winner.get("category_code"),
                "unresolved_query_id": None,
                "answer_source": "qna_semantic",
                "debug": {
                    "served_from": "qna_pair_semantic",
                    "qna_pair_id": winner["id"],
                    "semantic_score": winner.get("semantic_score"),
                    "query_info": {
                        "normalized_question": normalized_question,
                    },
                },
            })

        expert = store.find_expert_answer(
            question=question,
            normalized_question=normalized_question,
        )
        if expert:
            return _record_and_return({
                "answer": expert["expert_answer"],
                "grounded": True,
                "citations": [],
                "category": expert["category"],
                "predicted_category": expert["category"],
                "unresolved_query_id": None,
                "answer_source": "expert_exact",
                "debug": {
                    "served_from": "expert_answer",
                    "expert_answer_id": expert["id"],
                    "query_info": {
                        "normalized_question": normalized_question,
                    },
                },
            })

        routed_category = categories_service.predict_from_question(question)
        result = get_pipeline().ask(question, category_hint_override=routed_category)

        predicted_category = categories_service.infer(
            question,
            result.get("citations", []),
            routed_category,
        )

        answer_text = (result.get("answer") or "").strip()
        is_refusal = answer_text.lower() == REFUSAL_TEXT.lower()

        if is_refusal:
            unresolved_query_id = store.log_unresolved_query(
                question=question,
                normalized_question=normalized_question,
                category=predicted_category,
                answer_text=answer_text,
                reason="unresolved_or_not_in_docs",
                citations=result.get("citations", []),
            )

            result["unresolved_query_id"] = unresolved_query_id
            result["category"] = None
            result["answer_source"] = "unresolved"
        else:
            result["category"] = predicted_category
            result["unresolved_query_id"] = None

        result["predicted_category"] = predicted_category
        return _record_and_return(result)

    except FileNotFoundError:
        logger.exception("Missing retrieval index artifacts.")
        return JSONResponse(
            status_code=503,
            content={"error": "Retrieval index not available. Please run ingestion first."},
        )
    except Exception:
        logger.exception("Unhandled error while processing /api/ask.")
        return JSONResponse(
            status_code=500,
            content={"error": "Internal server error. Please try again later."},
        )

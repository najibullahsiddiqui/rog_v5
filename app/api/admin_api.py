from __future__ import annotations

from pathlib import Path
import io

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from openpyxl import Workbook

from app.core.admin_store import AdminStore
from app.core.category_utils import normalize_category
from app.core.pipeline import normalize_question_text


router = APIRouter(tags=["admin"])
store = AdminStore()

BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


# -----------------------------
# Models
# -----------------------------
class ExpertAnswerPayload(BaseModel):
    unresolved_query_id: int | None = None
    question: str
    normalized_question: str | None = None
    category: str
    expert_answer: str
    source_note: str | None = None


# -----------------------------
# UI ROUTE
# -----------------------------
@router.get("/admin", response_class=HTMLResponse)
def admin_dashboard(request: Request):
    return templates.TemplateResponse(
        "admin_dashboard.html",
        {"request": request},
    )


# -----------------------------
# DATA APIs
# -----------------------------
@router.get("/api/admin/summary")
def get_summary():
    return store.dashboard_summary()


@router.get("/api/admin/unresolved")
def get_unresolved(
    category: str | None = Query(default=None),
    status: str = Query(default="open"),
):
    norm = normalize_category(category) if category else None
    return {"items": store.list_unresolved(norm, status)}


@router.get("/api/admin/feedback")
def get_feedback(category: str | None = Query(default=None)):
    norm = normalize_category(category) if category else None
    return {"items": store.list_feedback(norm)}


# -----------------------------
# EXPERT ANSWER SAVE
# -----------------------------
@router.post("/api/admin/expert-answer")
def save_expert_answer(payload: ExpertAnswerPayload):
    category = normalize_category(payload.category)

    if not category:
        return {
            "ok": False,
            "message": "Invalid category",
        }

    normalized_question = normalize_question_text(
        payload.normalized_question or payload.question
    )

    expert_answer_id = store.save_expert_answer(
        question=payload.question,
        normalized_question=normalized_question,
        category=category,
        expert_answer=payload.expert_answer,
        source_note=payload.source_note,
        unresolved_query_id=payload.unresolved_query_id,
    )

    return {
        "ok": True,
        "expert_answer_id": expert_answer_id,
    }


# -----------------------------
# EXPORT: UNRESOLVED → EXCEL
# -----------------------------
@router.get("/api/admin/export/unresolved")
def export_unresolved(
    category: str | None = Query(default=None),
    status: str = Query(default="open"),
):
    norm = normalize_category(category) if category else None
    items = store.list_unresolved(norm, status)

    wb = Workbook()
    ws = wb.active
    ws.title = "Unresolved Queries"

    headers = ["ID", "Category", "Question", "Reason", "Created"]
    ws.append(headers)

    for item in items:
        ws.append([
            item.get("id"),
            item.get("final_category") or item.get("category"),
            item.get("question"),
            item.get("reason"),
            item.get("created_at"),
        ])

    stream = io.BytesIO()
    wb.save(stream)
    stream.seek(0)

    return StreamingResponse(
        stream,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": "attachment; filename=unresolved_queries.xlsx"
        },
    )


# -----------------------------
# EXPORT: FEEDBACK → EXCEL
# -----------------------------
@router.get("/api/admin/export/feedback")
def export_feedback(category: str | None = Query(default=None)):
    norm = normalize_category(category) if category else None
    items = store.list_feedback(norm)

    wb = Workbook()
    ws = wb.active
    ws.title = "User Feedback"

    headers = ["ID", "Category", "Question", "Status", "Comment", "Created"]
    ws.append(headers)

    for item in items:
        ws.append([
            item.get("id"),
            item.get("category"),
            item.get("question"),
            "Satisfied" if item.get("satisfied") else "Not satisfied",
            item.get("comment"),
            item.get("created_at"),
        ])

    stream = io.BytesIO()
    wb.save(stream)
    stream.seek(0)

    return StreamingResponse(
        stream,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": "attachment; filename=user_feedback.xlsx"
        },
    )
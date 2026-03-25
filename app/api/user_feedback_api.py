from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app.core.admin_store import AdminStore
from app.core.category_utils import normalize_category
from app.core.pipeline import normalize_question_text


router = APIRouter(tags=["feedback"])
store = AdminStore()


# -----------------------------
# Models
# -----------------------------
class FeedbackPayload(BaseModel):
    question: str
    normalized_question: str | None = None
    category: str | None = None
    answer_text: str
    satisfied: bool
    comment: str | None = None
    citations: list[dict] | None = None


# -----------------------------
# Save Feedback API
# -----------------------------
@router.post("/api/feedback")
def save_feedback(payload: FeedbackPayload):
    question = (payload.question or "").strip()

    if not question:
        return {
            "ok": False,
            "message": "Question is required",
        }

    # normalize question server-side (IMPORTANT)
    normalized_question = normalize_question_text(
        payload.normalized_question or question
    )

    category = normalize_category(payload.category) if payload.category else None

    feedback_id = store.save_feedback(
        question=question,
        normalized_question=normalized_question,
        category=category,
        answer_text=payload.answer_text,
        satisfied=payload.satisfied,
        comment=payload.comment,
        citations=payload.citations,
    )

    return {
        "ok": True,
        "feedback_id": feedback_id,
    }
from __future__ import annotations

from fastapi import APIRouter

from app.schemas import FeedbackPayload
from app.services import CategoriesService, ChatHistoryService
from app.core.pipeline import normalize_question_text


router = APIRouter(tags=["feedback"])
chat_history_service = ChatHistoryService()
categories_service = CategoriesService()


@router.post("/api/feedback")
def save_feedback(payload: FeedbackPayload):
    question = (payload.question or "").strip()

    if not question:
        return {
            "ok": False,
            "message": "Question is required",
        }

    normalized_question = normalize_question_text(
        payload.normalized_question or question
    )

    category = categories_service.normalize(payload.category) if payload.category else None

    feedback_id = chat_history_service.log_feedback(
        question=question,
        normalized_question=normalized_question,
        category=category,
        answer_text=payload.answer_text,
        satisfied=payload.satisfied,
        comment=payload.comment,
        citations=[c.model_dump() for c in payload.citations] if payload.citations else None,
    )

    return {
        "ok": True,
        "feedback_id": feedback_id,
    }

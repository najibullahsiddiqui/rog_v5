from __future__ import annotations

from fastapi import APIRouter

from app.schemas import FeedbackPayload, WrongAnswerReportPayload
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
        session_id=payload.session_id,
        message_id=payload.message_id,
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


@router.post("/api/feedback/wrong-answer")
def report_wrong_answer(payload: WrongAnswerReportPayload):
    question = (payload.question or "").strip()
    if not question:
        return {"ok": False, "message": "Question is required"}
    normalized_question = normalize_question_text(payload.normalized_question or question)
    category = categories_service.normalize(payload.category) if payload.category else None
    report_id = chat_history_service.log_wrong_answer_report(
        session_id=payload.session_id,
        message_id=payload.message_id,
        feedback_id=payload.feedback_id,
        question=question,
        normalized_question=normalized_question,
        category=category,
        answer_text=payload.answer_text or "",
        citations=[c.model_dump() for c in payload.citations] if payload.citations else None,
        note=payload.note,
        reason_code=payload.reason_code,
        severity=payload.severity,
    )
    return {"ok": True, "wrong_answer_report_id": report_id}

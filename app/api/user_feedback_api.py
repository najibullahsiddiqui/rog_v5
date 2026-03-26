from __future__ import annotations

import logging

from fastapi import APIRouter
from fastapi import HTTPException

from app.schemas import FeedbackPayload, WrongAnswerReportPayload
from app.services import CategoriesService, ChatHistoryService
from app.core.pipeline import normalize_question_text


router = APIRouter(tags=["feedback"])
chat_history_service = ChatHistoryService()
categories_service = CategoriesService()
logger = logging.getLogger(__name__)


@router.post("/api/feedback")
def save_feedback(payload: FeedbackPayload):
    question = (payload.question or "").strip()

    if not question:
        raise HTTPException(status_code=400, detail="Question is required")

    normalized_question = normalize_question_text(
        payload.normalized_question or question
    )

    category = categories_service.normalize(payload.category) if payload.category else None

    try:
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
    except Exception as exc:
        logger.exception("Failed to save feedback")
        raise HTTPException(status_code=500, detail="Failed to save feedback") from exc

    return {
        "ok": True,
        "feedback_id": feedback_id,
    }


@router.post("/api/feedback/wrong-answer")
def report_wrong_answer(payload: WrongAnswerReportPayload):
    question = (payload.question or "").strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question is required")
    normalized_question = normalize_question_text(payload.normalized_question or question)
    category = categories_service.normalize(payload.category) if payload.category else None
    try:
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
    except Exception as exc:
        logger.exception("Failed to save wrong-answer report")
        raise HTTPException(status_code=500, detail="Failed to save wrong-answer report") from exc
    return {"ok": True, "wrong_answer_report_id": report_id}

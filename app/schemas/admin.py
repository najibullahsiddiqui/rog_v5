from __future__ import annotations

from pydantic import BaseModel

from app.schemas.common import CitationSchema


class AdminRecordSchema(BaseModel):
    id: int
    question: str
    normalized_question: str | None = None
    category: str | None = None
    created_at: str | None = None


class FeedbackPayload(BaseModel):
    question: str
    normalized_question: str | None = None
    category: str | None = None
    answer_text: str
    satisfied: bool
    comment: str | None = None
    citations: list[CitationSchema] | None = None


class ExpertAnswerPayload(BaseModel):
    unresolved_query_id: int | None = None
    question: str
    normalized_question: str | None = None
    category: str
    expert_answer: str
    source_note: str | None = None


class UnresolvedCategoryPayload(BaseModel):
    unresolved_query_id: int
    user_selected_category: str


class DataSourceCreatePayload(BaseModel):
    name: str
    source_type: str = "manual_upload"
    source_format: str = "pdf"
    uri: str | None = None


class DataSourceStatusPayload(BaseModel):
    status: str

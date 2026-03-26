from __future__ import annotations

from pydantic import BaseModel, Field

from app.core.constants import ResponseMode
from app.schemas.common import CitationSchema, QueryClassificationResult


class AskRequest(BaseModel):
    question: str
    session_key: str | None = None


class AskResponse(BaseModel):
    answer: str
    grounded: bool
    citations: list[CitationSchema]
    category: str | None = None
    predicted_category: str | None = None
    unresolved_query_id: int | None = None
    answer_source: str | None = None
    response_mode: ResponseMode | None = None
    classification: QueryClassificationResult | None = None
    debug: dict | None = Field(default=None)

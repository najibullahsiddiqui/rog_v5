from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.core.constants import ResponseMode


class CitationSchema(BaseModel):
    doc_name: str
    page_no: int | None = None
    page_start: int | None = None
    page_end: int | None = None
    page_label: str | None = None
    heading: str | None = None
    excerpt: str
    score: float | None = None


class QueryClassificationResult(BaseModel):
    response_mode: ResponseMode
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    predicted_category: str | None = None
    reasons: list[str] = Field(default_factory=list)


class APIResponseSchema(BaseModel):
    ok: bool = True
    data: dict[str, Any] | None = None
    error: str | None = None


class AdminErrorSchema(BaseModel):
    ok: bool = False
    error_code: str
    message: str
    details: dict[str, Any] | None = None

from __future__ import annotations

from pydantic import BaseModel, Field

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


class JsonConvertPayload(BaseModel):
    target: str
    json_text: str


class QnaPairPayload(BaseModel):
    question: str
    answer: str
    category_code: str | None = None
    source_note: str | None = None
    is_exact_eligible: bool = True
    is_semantic_eligible: bool = True
    approval_status: str = "approved"
    priority: int = 0


class CategoryPayload(BaseModel):
    code: str
    name: str
    description: str | None = None
    display_order: int = 0
    is_active: bool = True
    routing_hint: str | None = None
    prompt_hint: str | None = None
    retrieval_scope: dict | None = None


class CategorySynonymPayload(BaseModel):
    synonym: str


class DecisionTreePayload(BaseModel):
    id: int | None = None
    tree_key: str | None = None
    name: str
    version: str = "1.0.0"
    status: str = "draft"
    description: str | None = None
    category_code: str | None = None
    is_active: bool = True
    trigger_phrases: list[str] = Field(default_factory=list)
    nodes: list[dict] = Field(default_factory=list)
    edges: list[dict] = Field(default_factory=list)


class TrainBotPromoteExpertPayload(BaseModel):
    unresolved_query_id: int
    category: str
    expert_answer: str
    source_note: str | None = None


class TrainBotPromoteQnaPayload(BaseModel):
    source_item_type: str
    source_item_id: int | None = None
    question: str
    answer: str
    category_code: str | None = None
    source_note: str | None = None


class TrainBotReindexPayload(BaseModel):
    data_source_id: int


class TrainBotCategoryRefreshPayload(BaseModel):
    category_code: str | None = None


class TrainBotResolveWrongAnswerPayload(BaseModel):
    report_id: int
    admin_action: str
    action_notes: str | None = None

from __future__ import annotations

from pydantic import BaseModel


class DataSource(BaseModel):
    id: int | None = None
    source_key: str
    name: str
    source_type: str
    status: str = "enabled"


class SourceDocument(BaseModel):
    id: int | None = None
    data_source_id: int
    doc_key: str
    file_name: str
    version: str | None = None
    content_hash: str | None = None
    chunk_count: int = 0
    status: str = "active"


class DocumentChunk(BaseModel):
    id: int | None = None
    source_document_id: int
    chunk_key: str
    chunk_index: int
    text: str
    normalized_text: str | None = None


class QnaPair(BaseModel):
    id: int | None = None
    question: str
    normalized_question: str
    answer: str
    is_exact_eligible: bool = True
    is_semantic_eligible: bool = True
    status: str = "active"


class TrainingJob(BaseModel):
    id: int | None = None
    job_type: str
    status: str = "queued"
    params_json: str | None = None


class IngestionJob(BaseModel):
    id: int | None = None
    data_source_id: int | None = None
    status: str = "queued"
    document_count: int = 0
    chunk_count: int = 0

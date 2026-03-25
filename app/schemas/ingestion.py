from __future__ import annotations

from pydantic import BaseModel


class IngestionJobSchema(BaseModel):
    job_name: str
    status: str
    source_count: int = 0
    index_present: bool = False
    message: str | None = None

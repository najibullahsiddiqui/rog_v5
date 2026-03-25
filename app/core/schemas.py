from pydantic import BaseModel
from typing import List

class AskRequest(BaseModel):
    question: str

class Citation(BaseModel):
    doc_name: str
    page_no: int
    heading: str | None = None
    excerpt: str
    score: float | None = None

class AskResponse(BaseModel):
    answer: str
    grounded: bool
    citations: List[Citation]
    debug: dict | None = None

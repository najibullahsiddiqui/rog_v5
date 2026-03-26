from __future__ import annotations

from app.core.config import INDEX_DIR, PDF_DIR
from app.schemas import IngestionJobSchema


class TrainingWorkflowsService:
    def ingestion_status(self) -> IngestionJobSchema:
        return IngestionJobSchema(
            job_name="document_ingestion",
            status="ready" if INDEX_DIR.exists() else "missing_index",
            source_count=len(list(PDF_DIR.glob("*.pdf"))),
            index_present=(INDEX_DIR / "faiss.index").exists(),
            message="Use scripts/ingest_pdfs.py to refresh index",
        )

from __future__ import annotations

from app.core.config import PDF_DIR


class DataSourcesService:
    def list_sources(self) -> list[str]:
        return sorted([p.name for p in PDF_DIR.glob('*.pdf')])

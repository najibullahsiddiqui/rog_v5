from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path


class Settings:
    def __init__(self) -> None:
        self.base_dir = Path(__file__).resolve().parents[2]
        self.data_dir = self.base_dir / "data"
        self.index_dir = self.data_dir / "index"
        self.pdf_dir = self.data_dir / "source_pdfs"
        self.models_dir = self.base_dir / "models"

        self.ollama_base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        self.ollama_model = os.getenv("OLLAMA_MODEL", "qwen2.5:7b-instruct")

        self._embedding_model_remote = os.getenv(
            "EMBEDDING_MODEL",
            "sentence-transformers/all-MiniLM-L6-v2",
        )
        self._reranker_model_remote = os.getenv(
            "RERANKER_MODEL",
            "cross-encoder/ms-marco-MiniLM-L-6-v2",
        )

        embed_model_path = Path(
            os.getenv(
                "EMBED_MODEL_PATH",
                str(self.models_dir / "embeddings" / "all-MiniLM-L6-v2"),
            )
        ).resolve()
        reranker_model_path = Path(
            os.getenv(
                "RERANKER_MODEL_PATH",
                str(self.models_dir / "rerankers" / "ms-marco-MiniLM-L-6-v2"),
            )
        ).resolve()

        self.embedding_model = (
            str(embed_model_path)
            if embed_model_path.exists()
            else self._embedding_model_remote
        )
        self.reranker_model = (
            str(reranker_model_path)
            if reranker_model_path.exists()
            else self._reranker_model_remote
        )

        self.top_k_vector = int(os.getenv("TOP_K_VECTOR", "15"))
        self.top_k_bm25 = int(os.getenv("TOP_K_BM25", "15"))
        self.top_k_rerank = int(os.getenv("TOP_K_RERANK", "8"))
        self.min_context_chars = int(os.getenv("MIN_CONTEXT_CHARS", "80"))
        self.min_rerank_score = float(os.getenv("MIN_RERANK_SCORE", "0.0"))


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()

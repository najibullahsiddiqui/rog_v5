from __future__ import annotations

from app.core.settings import get_settings


settings = get_settings()

BASE_DIR = settings.base_dir
DATA_DIR = settings.data_dir
INDEX_DIR = settings.index_dir
PDF_DIR = settings.pdf_dir
MODELS_DIR = settings.models_dir

OLLAMA_BASE_URL = settings.ollama_base_url
OLLAMA_MODEL = settings.ollama_model

EMBEDDING_MODEL = settings.embedding_model
RERANKER_MODEL = settings.reranker_model

TOP_K_VECTOR = settings.top_k_vector
TOP_K_BM25 = settings.top_k_bm25
TOP_K_RERANK = settings.top_k_rerank

MIN_CONTEXT_CHARS = settings.min_context_chars
MIN_RERANK_SCORE = settings.min_rerank_score

ADMIN_TOKEN = settings.admin_token
ADMIN_SESSION_COOKIE = settings.admin_session_cookie

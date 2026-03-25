from pathlib import Path
import os

BASE_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = BASE_DIR / "data"
INDEX_DIR = DATA_DIR / "index"
PDF_DIR = DATA_DIR / "source_pdfs"
MODELS_DIR = BASE_DIR / "models"

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:7b-instruct")

_EMBEDDING_MODEL_REMOTE = os.getenv(
    "EMBEDDING_MODEL",
    "sentence-transformers/all-MiniLM-L6-v2"
)
_RERANKER_MODEL_REMOTE = os.getenv(
    "RERANKER_MODEL",
    "cross-encoder/ms-marco-MiniLM-L-6-v2"
)

EMBED_MODEL_PATH = Path(
    os.getenv(
        "EMBED_MODEL_PATH",
        str(MODELS_DIR / "embeddings" / "all-MiniLM-L6-v2")
    )
).resolve()

RERANKER_MODEL_PATH = Path(
    os.getenv(
        "RERANKER_MODEL_PATH",
        str(MODELS_DIR / "rerankers" / "ms-marco-MiniLM-L-6-v2")
    )
).resolve()

EMBEDDING_MODEL = str(EMBED_MODEL_PATH) if EMBED_MODEL_PATH.exists() else _EMBEDDING_MODEL_REMOTE
RERANKER_MODEL = str(RERANKER_MODEL_PATH) if RERANKER_MODEL_PATH.exists() else _RERANKER_MODEL_REMOTE

TOP_K_VECTOR = int(os.getenv("TOP_K_VECTOR", "15"))
TOP_K_BM25 = int(os.getenv("TOP_K_BM25", "15"))
TOP_K_RERANK = int(os.getenv("TOP_K_RERANK", "8"))

MIN_CONTEXT_CHARS = int(os.getenv("MIN_CONTEXT_CHARS", "80"))
MIN_RERANK_SCORE = float(os.getenv("MIN_RERANK_SCORE", "0.0"))
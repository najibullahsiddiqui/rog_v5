from __future__ import annotations

import json
import sys
from pathlib import Path

# project root ko sys.path me daalo
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from sentence_transformers import SentenceTransformer
from app.core.ingestion import Chunk, build_index, save_outputs
from app.core.config import EMBEDDING_MODEL


def load_chunks(jsonl_path: Path):
    chunks = []
    with open(jsonl_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            chunks.append(Chunk(**row))
    return chunks


def main():
    # yahan apna actual hotfix file ya final chunks file do
    jsonl_path = PROJECT_ROOT / "data" / "index" / "chunks.jsonl"

    # agar demo hotfix file use karni hai to ye uncomment karke path badal do:
    # jsonl_path = PROJECT_ROOT / "chunks_demo_hotfix.jsonl"

    if not jsonl_path.exists():
        raise FileNotFoundError(f"chunks file not found: {jsonl_path}")

    chunks = load_chunks(jsonl_path)
    print(f"[INFO] Loaded chunks: {len(chunks)}")
    print(f"[INFO] Using embedding model: {EMBEDDING_MODEL}")

    embedder = SentenceTransformer(EMBEDDING_MODEL)
    index, bm25 = build_index(chunks, embedder)
    save_outputs(chunks, index, bm25)

    print("[DONE] Rebuilt faiss.index + bm25.pkl successfully.")


if __name__ == "__main__":
    main()
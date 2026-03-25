from sentence_transformers import CrossEncoder
from pathlib import Path

save_path = Path("models/rerankers/ms-marco-MiniLM-L-6-v2")
save_path.parent.mkdir(parents=True, exist_ok=True)

print("Downloading reranker...")
model = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")

print(f"Saving to {save_path}")
model.save(str(save_path))

print("Done.")
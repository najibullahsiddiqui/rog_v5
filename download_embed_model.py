from sentence_transformers import SentenceTransformer
from pathlib import Path

model_name = "sentence-transformers/all-MiniLM-L6-v2"
save_path = Path("models/embeddings/all-MiniLM-L6-v2")

save_path.parent.mkdir(parents=True, exist_ok=True)

print(f"Downloading model: {model_name}")
model = SentenceTransformer(model_name)

print(f"Saving model to: {save_path}")
model.save(str(save_path))

print("Done.")
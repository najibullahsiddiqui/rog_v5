from __future__ import annotations

import requests

from app.core.config import OLLAMA_BASE_URL, OLLAMA_MODEL


REFUSAL_TEXT = "The answer is not available in the approved document set."

SYSTEM_PROMPT = """
You are an official IP India assistant.

Rules:
1. Answer ONLY from the provided approved document context.
2. Direct FAQ exact-match answers are handled separately; in this step you are answering only paraphrased or non-exact questions.
3. If the context clearly supports the answer, synthesize a short, clear, Google-style response.
4. Do not copy large chunks verbatim.
5. Do not add legal advice, assumptions, or outside knowledge.
6. If the answer is not clearly supported by the context, reply exactly:
The answer is not available in the approved document set.
""".strip()


def generate_answer(question: str, context: str) -> str:
    prompt = f"""
Approved document context:
{context}

User question:
{question}

Task:
- Answer only from the approved context.
- The question may be phrased differently from the source document.
- If the answer is clearly supported, write a concise natural-language answer in 1-3 sentences.
- Prefer simple direct wording.
- Do not mention the context or the document in the answer.
- Do not quote large passages.
- If the answer is not clearly supported, reply exactly:
{REFUSAL_TEXT}

Answer:
""".strip()

    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "system": SYSTEM_PROMPT,
        "stream": False,
        "options": {
            "temperature": 0.0,
            "top_p": 0.9,
            "num_predict": 120,
        },
    }

    try:
        response = requests.post(
            f"{OLLAMA_BASE_URL}/api/generate",
            json=payload,
            timeout=60,
        )
        response.raise_for_status()
        data = response.json()
        answer = (data.get("response") or "").strip()
        return answer or REFUSAL_TEXT
    except Exception:
        return REFUSAL_TEXT
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.core.schemas import AskRequest
from app.core.pipeline import QAPipeline, normalize_question_text
from app.core.config import PDF_DIR
from app.core.admin_store import AdminStore
from app.core.category_utils import infer_category

from app.api.admin_api import router as admin_router
from app.api.user_feedback_api import router as feedback_router
from app.api.unresolved_category_api import router as unresolved_category_router


app = FastAPI(title="IP India Strict RAG Bot")

app.include_router(admin_router)
app.include_router(feedback_router)
app.include_router(unresolved_category_router)

store = AdminStore()
REFUSAL_TEXT = "The answer is not available in the approved document set."

BASE_DIR = Path(__file__).resolve().parent
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

pipeline: QAPipeline | None = None


def get_pipeline() -> QAPipeline:
    global pipeline
    if pipeline is None:
        pipeline = QAPipeline()
    return pipeline


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/pdf/{file_name:path}")
def open_pdf(file_name: str):
    pdf_path = (PDF_DIR / file_name).resolve()
    pdf_root = PDF_DIR.resolve()

    if not str(pdf_path).startswith(str(pdf_root)):
        raise HTTPException(status_code=400, detail="Invalid file path.")

    if not pdf_path.exists() or not pdf_path.is_file():
        raise HTTPException(status_code=404, detail="PDF not found.")

    return FileResponse(
        path=str(pdf_path),
        media_type="application/pdf",
        headers={"Content-Disposition": "inline"},
    )


@app.post("/api/ask")
def ask(payload: AskRequest):
    question = payload.question.strip()
    if not question:
        return JSONResponse(
            status_code=400,
            content={"error": "Question is required."},
        )

    normalized_question = normalize_question_text(question)

    try:
        expert = store.find_expert_answer(
            question=question,
            normalized_question=normalized_question,
        )
        if expert:
            return {
                "answer": expert["expert_answer"],
                "grounded": True,
                "citations": [],
                "category": expert["category"],
                "predicted_category": expert["category"],
                "unresolved_query_id": None,
                "answer_source": "expert_exact",
                "debug": {
                    "served_from": "expert_answer",
                    "expert_answer_id": expert["id"],
                    "query_info": {
                        "normalized_question": normalized_question,
                    },
                },
            }

        result = get_pipeline().ask(question)

        predicted_category = infer_category(
            question,
            result.get("citations", []),
            None,
        )

        answer_text = (result.get("answer") or "").strip()
        is_refusal = answer_text.lower() == REFUSAL_TEXT.lower()

        if is_refusal:
            unresolved_query_id = store.log_unresolved_query(
                question=question,
                normalized_question=normalized_question,
                category=predicted_category,
                answer_text=answer_text,
                reason="unresolved_or_not_in_docs",
                citations=result.get("citations", []),
            )

            result["unresolved_query_id"] = unresolved_query_id
            result["category"] = None
            result["answer_source"] = "unresolved"
        else:
            result["category"] = predicted_category
            result["unresolved_query_id"] = None

        result["predicted_category"] = predicted_category
        return result

    except FileNotFoundError as exc:
        return JSONResponse(
            status_code=503,
            content={"error": str(exc)},
        )
    except Exception as exc:
        return JSONResponse(
            status_code=500,
            content={"error": f"Internal error: {exc}"},
        )
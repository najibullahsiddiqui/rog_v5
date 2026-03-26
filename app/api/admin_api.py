from __future__ import annotations

import io
import json
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from openpyxl import Workbook

from app.schemas import (
    DataSourceCreatePayload,
    DataSourceStatusPayload,
    ExpertAnswerPayload,
    JsonConvertPayload,
)
from app.services import AnalyticsService, CategoriesService, ExpertAnswersService
from app.repositories import AdminRepository
from app.core.pipeline import normalize_question_text


router = APIRouter(tags=["admin"])
admin_repository = AdminRepository()
analytics_service = AnalyticsService(admin_repository)
expert_answers_service = ExpertAnswersService(admin_repository)
categories_service = CategoriesService()

BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


@router.get("/admin", response_class=HTMLResponse)
def admin_dashboard(request: Request):
    return templates.TemplateResponse(
        "admin_dashboard.html",
        {"request": request},
    )


@router.get("/api/admin/summary")
def get_summary():
    return analytics_service.summary()


@router.get("/admin/analytics", response_class=HTMLResponse)
def admin_analytics(request: Request):
    return templates.TemplateResponse(
        "admin_analytics.html",
        {"request": request},
    )


@router.get("/api/admin/dashboard-summary")
def get_dashboard_summary():
    return analytics_service.dashboard_summary()


@router.get("/api/admin/analytics")
def get_analytics(range_days: int = Query(default=30, ge=1, le=365)):
    return analytics_service.analytics_breakdown(range_days=range_days)


@router.get("/api/admin/unresolved")
def get_unresolved(
    category: str | None = Query(default=None),
    status: str = Query(default="open"),
):
    norm = categories_service.normalize(category) if category else None
    return {"items": admin_repository.list_unresolved(norm, status)}


@router.get("/api/admin/feedback")
def get_feedback(category: str | None = Query(default=None)):
    norm = categories_service.normalize(category) if category else None
    return {"items": admin_repository.list_feedback(norm)}


@router.get("/api/admin/data-sources")
def list_data_sources():
    return {"items": admin_repository.list_data_sources()}


@router.post("/api/admin/data-sources")
def create_data_source(payload: DataSourceCreatePayload):
    allowed_source_types = {"pdf_folder", "manual_upload", "api", "database", "s3", "gdrive"}
    if payload.source_type not in allowed_source_types:
        raise HTTPException(status_code=400, detail="Unsupported source_type")

    source_id = admin_repository.create_data_source(
        name=payload.name.strip(),
        source_type=payload.source_type,
        source_format=(payload.source_format or "unknown").strip().lower(),
        uri=(payload.uri or "").strip() or None,
    )
    return {"ok": True, "source_id": source_id}


@router.get("/api/admin/data-sources/{data_source_id}/documents")
def list_source_documents(data_source_id: int):
    return {"items": admin_repository.list_source_documents(data_source_id)}


@router.post("/api/admin/data-sources/{data_source_id}/status")
def set_data_source_status(data_source_id: int, payload: DataSourceStatusPayload):
    if payload.status not in {"enabled", "disabled"}:
        raise HTTPException(status_code=400, detail="Invalid status")
    admin_repository.set_data_source_status(data_source_id, payload.status)
    return {"ok": True}


@router.post("/api/admin/data-sources/{data_source_id}/reingest")
def trigger_reingest(data_source_id: int):
    job_id = admin_repository.queue_reingest(data_source_id)
    return {"ok": True, "ingestion_job_id": job_id, "status": "queued"}


def _parse_json_records(json_text: str) -> tuple[list[dict], list[str]]:
    errors: list[str] = []
    try:
        payload = json.loads(json_text)
    except json.JSONDecodeError as exc:
        return [], [f"Invalid JSON: {exc.msg} at line {exc.lineno}, column {exc.colno}"]

    if isinstance(payload, dict):
        records = payload.get("records")
        if records is None:
            records = [payload]
    elif isinstance(payload, list):
        records = payload
    else:
        return [], ["JSON must be an object or array of objects"]

    if not isinstance(records, list):
        return [], ["Expected 'records' to be a list"]

    normalized: list[dict] = []
    for i, item in enumerate(records):
        if not isinstance(item, dict):
            errors.append(f"Row {i + 1}: expected object")
            continue
        normalized.append(item)
    return normalized, errors


def _required_fields_for_target(target: str) -> list[str]:
    return {
        "qna_pairs": ["question", "answer"],
        "categories": ["code", "name"],
        "decision_trees": ["name", "nodes"],
        "knowledge_docs": ["title", "content"],
    }.get(target, [])


@router.post("/api/admin/json-convert/preview")
def preview_json_convert(payload: JsonConvertPayload):
    target = (payload.target or "").strip()
    if target not in {"qna_pairs", "categories", "decision_trees", "knowledge_docs"}:
        raise HTTPException(status_code=400, detail="Unsupported target")

    records, parse_errors = _parse_json_records(payload.json_text or "")
    mapping_fields = _required_fields_for_target(target)
    errors = list(parse_errors)

    preview: list[dict] = []
    for idx, record in enumerate(records):
        row_missing = [f for f in mapping_fields if f not in record or record.get(f) in (None, "")]
        if row_missing:
            errors.append(f"Row {idx + 1}: missing required fields: {', '.join(row_missing)}")

        mapped = {f: record.get(f) for f in mapping_fields}
        extra_keys = [k for k in record.keys() if k not in mapping_fields][:8]
        preview.append(
            {
                "row": idx + 1,
                "mapped": mapped,
                "extra_fields": extra_keys,
            }
        )

    return {
        "ok": len(errors) == 0,
        "target": target,
        "record_count": len(records),
        "mapping_fields": mapping_fields,
        "preview": preview[:100],
        "errors": errors,
    }


@router.post("/api/admin/json-convert/import")
def import_json_convert(payload: JsonConvertPayload):
    target = (payload.target or "").strip()
    if target not in {"qna_pairs", "categories", "decision_trees", "knowledge_docs"}:
        raise HTTPException(status_code=400, detail="Unsupported target")

    records, parse_errors = _parse_json_records(payload.json_text or "")
    if parse_errors:
        audit_id = admin_repository.log_import_audit(
            action="json_convert_import",
            target=target,
            status="failed_parse",
            created_count=0,
            error_count=len(parse_errors),
            metadata={"errors": parse_errors},
        )
        return {"ok": False, "created_count": 0, "errors": parse_errors, "audit_log_id": audit_id}

    if target == "qna_pairs":
        created, errors = admin_repository.import_qna_pairs(records)
    elif target == "categories":
        created, errors = admin_repository.import_categories(records)
    elif target == "decision_trees":
        created, errors = admin_repository.import_decision_trees(records)
    else:
        created, errors = admin_repository.import_knowledge_docs(records)

    audit_id = admin_repository.log_import_audit(
        action="json_convert_import",
        target=target,
        status="success" if not errors else "partial",
        created_count=created,
        error_count=len(errors),
        metadata={"record_count": len(records), "errors": errors[:50]},
    )
    return {
        "ok": len(errors) == 0,
        "target": target,
        "created_count": created,
        "error_count": len(errors),
        "errors": errors,
        "audit_log_id": audit_id,
    }


@router.post("/api/admin/expert-answer")
def save_expert_answer(payload: ExpertAnswerPayload):
    category = categories_service.normalize(payload.category)

    if not category:
        return {
            "ok": False,
            "message": "Invalid category",
        }

    normalized_question = normalize_question_text(
        payload.normalized_question or payload.question
    )

    expert_answer_id = expert_answers_service.save(
        question=payload.question,
        normalized_question=normalized_question,
        category=category,
        expert_answer=payload.expert_answer,
        source_note=payload.source_note,
        unresolved_query_id=payload.unresolved_query_id,
    )

    return {
        "ok": True,
        "expert_answer_id": expert_answer_id,
    }


@router.get("/api/admin/export/unresolved")
def export_unresolved(
    category: str | None = Query(default=None),
    status: str = Query(default="open"),
):
    norm = categories_service.normalize(category) if category else None
    items = admin_repository.list_unresolved(norm, status)

    wb = Workbook()
    ws = wb.active
    ws.title = "Unresolved Queries"

    headers = ["ID", "Category", "Question", "Reason", "Created"]
    ws.append(headers)

    for item in items:
        ws.append([
            item.get("id"),
            item.get("final_category") or item.get("category"),
            item.get("question"),
            item.get("reason"),
            item.get("created_at"),
        ])

    stream = io.BytesIO()
    wb.save(stream)
    stream.seek(0)

    return StreamingResponse(
        stream,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": "attachment; filename=unresolved_queries.xlsx"
        },
    )


@router.get("/api/admin/export/feedback")
def export_feedback(category: str | None = Query(default=None)):
    norm = categories_service.normalize(category) if category else None
    items = admin_repository.list_feedback(norm)

    wb = Workbook()
    ws = wb.active
    ws.title = "User Feedback"

    headers = ["ID", "Category", "Question", "Status", "Comment", "Created"]
    ws.append(headers)

    for item in items:
        ws.append([
            item.get("id"),
            item.get("category"),
            item.get("question"),
            "Satisfied" if item.get("satisfied") else "Not satisfied",
            item.get("comment"),
            item.get("created_at"),
        ])

    stream = io.BytesIO()
    wb.save(stream)
    stream.seek(0)

    return StreamingResponse(
        stream,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": "attachment; filename=user_feedback.xlsx"
        },
    )

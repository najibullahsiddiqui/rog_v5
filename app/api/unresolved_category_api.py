from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app.core.admin_store import AdminStore
from app.core.category_utils import normalize_category


router = APIRouter(prefix="/api", tags=["unresolved-category"])
store = AdminStore()


class UnresolvedCategoryPayload(BaseModel):
    unresolved_query_id: int
    user_selected_category: str


@router.post("/unresolved-category")
def update_unresolved_category(payload: UnresolvedCategoryPayload):
    category = normalize_category(payload.user_selected_category)
    if not category:
        return {
            "ok": False,
            "message": "Invalid category",
        }

    store.update_unresolved_category(
        unresolved_query_id=payload.unresolved_query_id,
        user_selected_category=category,
    )

    return {
        "ok": True,
        "category": category,
    }
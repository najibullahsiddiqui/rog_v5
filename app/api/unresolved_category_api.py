from __future__ import annotations

from fastapi import APIRouter

from app.schemas import UnresolvedCategoryPayload
from app.repositories import AdminRepository
from app.services import CategoriesService


router = APIRouter(prefix="/api", tags=["unresolved-category"])
admin_repository = AdminRepository()
categories_service = CategoriesService()


@router.post("/unresolved-category")
def update_unresolved_category(payload: UnresolvedCategoryPayload):
    category = categories_service.normalize(payload.user_selected_category)
    if not category:
        return {
            "ok": False,
            "message": "Invalid category",
        }

    admin_repository.update_unresolved_category(
        unresolved_query_id=payload.unresolved_query_id,
        user_selected_category=category,
    )

    return {
        "ok": True,
        "category": category,
    }

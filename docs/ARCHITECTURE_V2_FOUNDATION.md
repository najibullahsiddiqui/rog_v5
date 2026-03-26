# V2 Foundation Refactor (Enterprise-Ready Baseline)

This refactor introduces stable service/repository/schema boundaries while preserving current user-facing behavior.

## New module boundaries

- `app/services/answer_engine_service.py`
- `app/services/retrieval_service.py`
- `app/services/expert_answers_service.py`
- `app/services/categories_service.py`
- `app/services/data_sources_service.py`
- `app/services/decision_tree_service.py`
- `app/services/analytics_service.py`
- `app/services/chat_history_service.py`
- `app/services/training_workflows_service.py`

## Shared contracts

- Response mode enum: `app/core/constants.py` (`exact_faq`, `near_faq`, `expert_answer`, `decision_tree`, `grounded_synthesis`, `unresolved`)
- Standard API/admin schemas: `app/schemas/common.py`
- Citation schema: `app/schemas/common.py`
- Query classification schema: `app/schemas/common.py`
- Ask/admin payload schemas: `app/schemas/qna.py`, `app/schemas/admin.py`
- Ingestion job schema: `app/schemas/ingestion.py`

## Centralized configuration

- New settings loader: `app/core/settings.py`
- `app/core/config.py` now acts as a compatibility bridge to shared settings.

## Compatibility notes

- Existing routes remain in place.
- Existing database tables and retrieval pipeline are unchanged.
- `app/core/schemas.py` re-exports from `app/schemas` for backward compatibility.

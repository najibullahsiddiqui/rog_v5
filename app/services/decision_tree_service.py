from __future__ import annotations

from app.core.constants import ResponseMode


class DecisionTreeService:
    """Placeholder decision entrypoint backed by deterministic logic."""

    def classify(self, question: str) -> ResponseMode:
        if "if" in (question or "").lower() and "then" in (question or "").lower():
            return ResponseMode.DECISION_TREE
        return ResponseMode.GROUNDED_SYNTHESIS

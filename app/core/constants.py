from __future__ import annotations

from enum import Enum


REFUSAL_TEXT = "The answer is not available in the approved document set."


class ResponseMode(str, Enum):
    EXACT_FAQ = "exact_faq"
    NEAR_FAQ = "near_faq"
    EXPERT_ANSWER = "expert_answer"
    DECISION_TREE = "decision_tree"
    GROUNDED_SYNTHESIS = "grounded_synthesis"
    UNRESOLVED = "unresolved"

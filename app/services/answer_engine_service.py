from __future__ import annotations

from app.core.constants import REFUSAL_TEXT, ResponseMode
from app.core.pipeline import QAPipeline, normalize_question_text
from app.schemas import QueryClassificationResult
from app.services.categories_service import CategoriesService
from app.services.expert_answers_service import ExpertAnswersService


class AnswerEngineService:
    def __init__(
        self,
        pipeline: QAPipeline | None = None,
        expert_answers: ExpertAnswersService | None = None,
        categories: CategoriesService | None = None,
    ):
        self.pipeline = pipeline or QAPipeline()
        self.expert_answers = expert_answers or ExpertAnswersService()
        self.categories = categories or CategoriesService()

    def ask(self, question: str, log_unresolved_fn) -> dict:
        normalized_question = normalize_question_text(question)

        expert = self.expert_answers.find_exact(question, normalized_question)
        if expert:
            classification = QueryClassificationResult(
                response_mode=ResponseMode.EXPERT_ANSWER,
                confidence=1.0,
                predicted_category=expert["category"],
                reasons=["exact expert answer match"],
            )
            return {
                "answer": expert["expert_answer"],
                "grounded": True,
                "citations": [],
                "category": expert["category"],
                "predicted_category": expert["category"],
                "unresolved_query_id": None,
                "answer_source": "expert_exact",
                "response_mode": ResponseMode.EXPERT_ANSWER.value,
                "classification": classification.model_dump(),
                "debug": {
                    "served_from": "expert_answer",
                    "expert_answer_id": expert["id"],
                    "query_info": {
                        "normalized_question": normalized_question,
                    },
                },
            }

        result = self.pipeline.ask(question)
        predicted_category = self.categories.infer(question, result.get("citations", []), None)

        answer_text = (result.get("answer") or "").strip()
        is_refusal = answer_text.lower() == REFUSAL_TEXT.lower()

        if is_refusal:
            unresolved_query_id = log_unresolved_fn(
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
            response_mode = ResponseMode.UNRESOLVED
        else:
            result["category"] = predicted_category
            result["unresolved_query_id"] = None
            if result.get("answer_source") == "faq_exact":
                response_mode = ResponseMode.EXACT_FAQ
            else:
                response_mode = ResponseMode.GROUNDED_SYNTHESIS

        result["predicted_category"] = predicted_category
        result["response_mode"] = response_mode.value
        result["classification"] = QueryClassificationResult(
            response_mode=response_mode,
            confidence=1.0 if response_mode != ResponseMode.GROUNDED_SYNTHESIS else 0.75,
            predicted_category=predicted_category,
            reasons=[result.get("answer_source", "pipeline")],
        ).model_dump()
        return result

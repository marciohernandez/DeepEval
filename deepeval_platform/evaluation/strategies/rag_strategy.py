"""RAGStrategy — metric set for RAG bots (M2.1, FR-006)."""
from __future__ import annotations

from deepeval_platform.evaluation.strategy_base import EvaluationStrategyBase


class RAGStrategy(EvaluationStrategyBase):
    """Metric set for RAG bots (FR-006).

    Covers retrieval quality (precision/recall/relevancy) and generation
    fidelity (faithfulness, answer relevancy).
    """

    def get_metrics(self) -> list[str]:
        return [
            "answer_relevancy",
            "faithfulness",
            "contextual_precision",
            "contextual_recall",
            "contextual_relevancy",
        ]

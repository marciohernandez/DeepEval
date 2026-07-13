"""ConversationStrategy — metric set for multi-turn conversational bots (M2.1, FR-008)."""
from __future__ import annotations

from deepeval_platform.evaluation.strategy_base import EvaluationStrategyBase


class ConversationStrategy(EvaluationStrategyBase):
    """Metric set for multi-turn conversational bots (FR-008).

    Covers multi-turn coherence and per-turn relevancy.
    """

    def get_metrics(self) -> list[str]:
        return ["conversation_completeness", "turn_relevancy"]

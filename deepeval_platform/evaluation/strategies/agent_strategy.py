"""AgentStrategy — metric set for agentive bots (M2.1, FR-007)."""
from __future__ import annotations

from deepeval_platform.evaluation.strategy_base import EvaluationStrategyBase


class AgentStrategy(EvaluationStrategyBase):
    """Metric set for agentive bots (FR-007).

    Covers tool selection accuracy and end-to-end task success.
    """

    def get_metrics(self) -> list[str]:
        return ["tool_correctness", "task_completion", "bias", "toxicity"]

"""EvaluationStrategyBase — bot evaluation strategy interface (M2.1)."""
from __future__ import annotations

from abc import ABC, abstractmethod


class EvaluationStrategyBase(ABC):
    """Abstract base for all bot evaluation strategies (Strategy pattern).

    Each concrete strategy encapsulates the metric set appropriate for one bot type.
    Metric *instantiation* (thresholds, LLM judge) is deferred to MetricFactory (M3).

    Extension contract (FR-011, SC-002):
    - Adding a new bot type requires exactly one new subclass + one registry entry.
    - Zero changes to existing strategy implementations.
    """

    @abstractmethod
    def get_metrics(self) -> list[str]:
        """Return the ordered list of canonical DeepEval metric name strings.

        Returns:
            Non-empty list of canonical metric names, stable across calls.
            Examples: "answer_relevancy", "faithfulness", "tool_correctness"
        """

"""Contract: EvaluationStrategyBase, BotType, StrategyFactory (M2.1).

This file defines the public interface surface — not runnable production code.
The real implementations live in deepeval/evaluation/.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum
from typing import ClassVar


class BotType(str, Enum):
    """Supported bot classification types.

    Values are lowercase for direct YAML round-trip compatibility with bots.yaml.

    Coercion:
        BotType("rag")        → BotType.RAG      ✓
        BotType("unknown")    → ValueError        ✗ (caught by StrategyFactory)
        BotType(None)         → ValueError        ✗ (caught by StrategyFactory)
        BotType("")           → ValueError        ✗ (caught by StrategyFactory)

    No special-case branches for None/"" — BotType() coercion handles all uniformly.
    """
    RAG = "rag"
    AGENT = "agent"
    CONVERSATION = "conversation"


class InvalidBotTypeError(ValueError):
    """Raised by StrategyFactory when the bot type cannot be coerced to BotType.

    Message includes the received value and the full list of supported values,
    so callers can surface a descriptive error without additional formatting.
    """

    def __init__(self, received: object) -> None:
        supported = [bt.value for bt in BotType]
        super().__init__(
            f"Unrecognized bot type {received!r}. "
            f"Supported values: {supported}"
        )
        self.received = received
        self.supported = supported


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


class RAGStrategy(EvaluationStrategyBase):
    """Metric set for RAG bots (FR-006).

    Returns: ["answer_relevancy", "faithfulness", "contextual_precision",
              "contextual_recall", "contextual_relevancy"]
    """
    def get_metrics(self) -> list[str]: ...


class AgentStrategy(EvaluationStrategyBase):
    """Metric set for agentive bots (FR-007).

    Returns: ["tool_correctness", "task_completion"]
    """
    def get_metrics(self) -> list[str]: ...


class ConversationStrategy(EvaluationStrategyBase):
    """Metric set for multi-turn conversational bots (FR-008).

    Returns: ["conversation_completeness", "turn_relevancy"]
    """
    def get_metrics(self) -> list[str]: ...


class StrategyFactory:
    """Factory that maps BotType → EvaluationStrategyBase instance (FR-009, FR-010).

    Registry is a class-level dict. Adding a new strategy = one new entry.
    """

    _registry: ClassVar[dict[BotType, type[EvaluationStrategyBase]]] = {
        BotType.RAG: RAGStrategy,
        BotType.AGENT: AgentStrategy,
        BotType.CONVERSATION: ConversationStrategy,
    }

    @classmethod
    def create(cls, bot_type: BotType | str) -> EvaluationStrategyBase:
        """Instantiate and return the strategy for bot_type.

        Args:
            bot_type: A BotType instance or a raw string coercible to BotType.

        Returns:
            A concrete EvaluationStrategyBase instance.

        Raises:
            InvalidBotTypeError: If bot_type cannot be coerced to BotType
                (unrecognized string, None, empty string).
        """

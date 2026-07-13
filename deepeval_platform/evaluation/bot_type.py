"""BotType and InvalidBotTypeError — evaluation-layer classification (M2.1)."""
from __future__ import annotations

from enum import Enum


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

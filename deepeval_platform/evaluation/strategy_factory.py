"""StrategyFactory — maps BotType to EvaluationStrategyBase instances (M2.1)."""
from __future__ import annotations

from typing import ClassVar

from deepeval_platform.evaluation.bot_type import BotType, InvalidBotTypeError
from deepeval_platform.evaluation.strategies.agent_strategy import AgentStrategy
from deepeval_platform.evaluation.strategies.conversation_strategy import ConversationStrategy
from deepeval_platform.evaluation.strategies.rag_strategy import RAGStrategy
from deepeval_platform.evaluation.strategy_base import EvaluationStrategyBase


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
        try:
            coerced = BotType(bot_type)
        except ValueError as exc:
            raise InvalidBotTypeError(bot_type) from exc
        return cls._registry[coerced]()

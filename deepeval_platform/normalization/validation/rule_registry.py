"""ValidationRule — registry facade mapping BotType to ValidationRuleBase (M2.2, mirrors StrategyFactory)."""
from __future__ import annotations

from typing import ClassVar

from deepeval_platform.evaluation.bot_type import BotType, InvalidBotTypeError
from deepeval_platform.normalization.models import NormalizedTrace
from deepeval_platform.normalization.validation.result import ValidationResult
from deepeval_platform.normalization.validation.rule_base import ValidationRuleBase
from deepeval_platform.normalization.validation.rules.agent_rule import AgentValidationRule
from deepeval_platform.normalization.validation.rules.conversation_rule import (
    ConversationValidationRule,
)
from deepeval_platform.normalization.validation.rules.rag_rule import RagValidationRule


class ValidationRule:
    """Registry facade — public entry point matching FR-006's contract.

    Registry is a class-level dict. Adding a new BotType's rule = one new entry.
    """

    _REGISTRY: ClassVar[dict[BotType, ValidationRuleBase]] = {
        BotType.RAG: RagValidationRule(),
        BotType.AGENT: AgentValidationRule(),
        BotType.CONVERSATION: ConversationValidationRule(),
    }

    @classmethod
    def check(cls, trace: NormalizedTrace, bot_type: BotType | str) -> ValidationResult:
        """Validate trace against bot_type's minimum-field rule.

        Raises:
            InvalidBotTypeError: bot_type cannot be coerced to a known BotType.
        """
        try:
            coerced = BotType(bot_type)
        except ValueError as exc:
            raise InvalidBotTypeError(bot_type) from exc
        return cls._REGISTRY[coerced].validate(trace)

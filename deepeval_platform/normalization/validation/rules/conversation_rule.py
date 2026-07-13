"""ConversationValidationRule — minimum-field rule for conversation bots (M2.2, US3)."""
from __future__ import annotations

from deepeval_platform.normalization.validation.rule_base import ValidationRuleBase


class ConversationValidationRule(ValidationRuleBase):
    def required_fields(self) -> list[str]:
        return ["messages"]

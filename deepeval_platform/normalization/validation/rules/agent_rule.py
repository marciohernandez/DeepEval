"""AgentValidationRule — minimum-field rule for agent bots (M2.2, US3)."""
from __future__ import annotations

from deepeval_platform.normalization.validation.rule_base import ValidationRuleBase


class AgentValidationRule(ValidationRuleBase):
    def required_fields(self) -> list[str]:
        return ["input", "output", "tools_called"]

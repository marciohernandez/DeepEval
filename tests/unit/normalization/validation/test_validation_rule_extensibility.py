"""Extensibility proof for ValidationRule (M2.2, US3 — FR-008).

Defines a throwaway ValidationRuleBase subclass and registers it through the
same extension mechanism a real new bot type's rule would use (subclass +
overridden _REGISTRY), confirming the built-in RagValidationRule/
AgentValidationRule/ConversationValidationRule resolution is unaffected on the
real ValidationRule. No new production code — mirrors
test_strategy_factory_extensibility.py's _ExtendedFactory pattern.
"""
from __future__ import annotations

from deepeval_platform.evaluation.bot_type import BotType
from deepeval_platform.normalization.models import NormalizedTrace
from deepeval_platform.normalization.validation.result import ValidationResult
from deepeval_platform.normalization.validation.rule_base import ValidationRuleBase
from deepeval_platform.normalization.validation.rule_registry import ValidationRule
from deepeval_platform.normalization.validation.rules.agent_rule import AgentValidationRule
from deepeval_platform.normalization.validation.rules.conversation_rule import (
    ConversationValidationRule,
)
from deepeval_platform.normalization.validation.rules.rag_rule import RagValidationRule


class _ThrowawayValidationRule(ValidationRuleBase):
    """Minimal extension-point rule defined at test scope only."""

    def required_fields(self) -> list[str]:
        return ["input"]


class _ExtendedValidationRule(ValidationRule):
    """Test-local registry demonstrating the one-file + one-entry extension contract."""

    _REGISTRY = {**ValidationRule._REGISTRY, BotType.RAG: _ThrowawayValidationRule()}


class TestValidationRuleExtensibility:
    def test_extended_registry_resolves_new_rule(self):
        trace = NormalizedTrace(input="Q")

        result = _ExtendedValidationRule.check(trace, BotType.RAG)

        assert result == ValidationResult(is_valid=True, missing_fields=[])

    def test_real_registry_unaffected_by_extension(self):
        trace = NormalizedTrace(input="Q", output="A", context=[], expected_output="E")

        result = ValidationRule.check(trace, BotType.RAG)

        assert isinstance(ValidationRule._REGISTRY[BotType.RAG], RagValidationRule)
        assert result.is_valid is False
        assert "context" in result.missing_fields

    def test_extended_registry_still_resolves_untouched_entries(self):
        assert isinstance(_ExtendedValidationRule._REGISTRY[BotType.AGENT], AgentValidationRule)
        assert isinstance(
            _ExtendedValidationRule._REGISTRY[BotType.CONVERSATION], ConversationValidationRule
        )

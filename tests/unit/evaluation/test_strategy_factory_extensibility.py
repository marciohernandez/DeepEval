"""Extensibility proof for StrategyFactory (US3 — FR-011, SC-002).

Defines a throwaway EvaluationStrategyBase subclass and registers it through
the same extension mechanism a real new bot type would use (subclass +
overridden _registry), confirming the built-in RAGStrategy/AgentStrategy/
ConversationStrategy resolution is unaffected on the real StrategyFactory.
"""
from __future__ import annotations

from deepeval_platform.evaluation.bot_type import BotType
from deepeval_platform.evaluation.strategies.agent_strategy import AgentStrategy
from deepeval_platform.evaluation.strategies.conversation_strategy import ConversationStrategy
from deepeval_platform.evaluation.strategies.rag_strategy import RAGStrategy
from deepeval_platform.evaluation.strategy_base import EvaluationStrategyBase
from deepeval_platform.evaluation.strategy_factory import StrategyFactory


class _ThrowawayStrategy(EvaluationStrategyBase):
    """Minimal extension-point strategy defined at test scope only."""

    def get_metrics(self) -> list[str]:
        return ["custom_metric_a", "custom_metric_b"]


class _ExtendedFactory(StrategyFactory):
    """Test-local factory demonstrating the one-file + one-entry extension contract."""

    _registry = {**StrategyFactory._registry, BotType.RAG: _ThrowawayStrategy}


class TestStrategyFactoryExtensibility:
    def test_extended_factory_resolves_new_strategy(self):
        result = _ExtendedFactory.create(BotType.RAG)
        assert isinstance(result, _ThrowawayStrategy)
        assert result.get_metrics() == ["custom_metric_a", "custom_metric_b"]

    def test_real_factory_unaffected_by_extension(self):
        """Acceptance Scenario 1: existing strategies remain unaffected."""
        assert isinstance(StrategyFactory.create(BotType.RAG), RAGStrategy)
        assert isinstance(StrategyFactory.create(BotType.AGENT), AgentStrategy)
        assert isinstance(StrategyFactory.create(BotType.CONVERSATION), ConversationStrategy)

    def test_extended_factory_still_resolves_untouched_entries(self):
        assert isinstance(_ExtendedFactory.create(BotType.AGENT), AgentStrategy)
        assert isinstance(_ExtendedFactory.create(BotType.CONVERSATION), ConversationStrategy)

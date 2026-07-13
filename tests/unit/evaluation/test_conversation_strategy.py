"""Unit tests for ConversationStrategy (US2 — Metric Selection, FR-008)."""
from __future__ import annotations

from deepeval_platform.evaluation.strategies.agent_strategy import AgentStrategy
from deepeval_platform.evaluation.strategies.conversation_strategy import ConversationStrategy
from deepeval_platform.evaluation.strategies.rag_strategy import RAGStrategy
from deepeval_platform.evaluation.strategy_base import EvaluationStrategyBase


class TestConversationStrategy:
    def test_is_evaluation_strategy_base_subclass(self):
        assert issubclass(ConversationStrategy, EvaluationStrategyBase)

    def test_returns_non_empty_list(self):
        metrics = ConversationStrategy().get_metrics()
        assert isinstance(metrics, list)
        assert len(metrics) > 0

    def test_all_entries_are_strings(self):
        metrics = ConversationStrategy().get_metrics()
        assert all(isinstance(m, str) for m in metrics)

    def test_stable_across_calls(self):
        strategy = ConversationStrategy()
        assert strategy.get_metrics() == strategy.get_metrics()

    def test_contains_expected_metric_names(self):
        metrics = ConversationStrategy().get_metrics()
        assert metrics == ["conversation_completeness", "turn_relevancy"]

    def test_distinct_from_rag_strategy(self):
        assert set(ConversationStrategy().get_metrics()) != set(RAGStrategy().get_metrics())

    def test_distinct_from_agent_strategy(self):
        assert set(ConversationStrategy().get_metrics()) != set(AgentStrategy().get_metrics())

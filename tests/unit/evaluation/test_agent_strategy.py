"""Unit tests for AgentStrategy (US2 — Metric Selection, FR-007)."""
from __future__ import annotations

from deepeval_platform.evaluation.strategies.agent_strategy import AgentStrategy
from deepeval_platform.evaluation.strategies.rag_strategy import RAGStrategy
from deepeval_platform.evaluation.strategy_base import EvaluationStrategyBase


class TestAgentStrategy:
    def test_is_evaluation_strategy_base_subclass(self):
        assert issubclass(AgentStrategy, EvaluationStrategyBase)

    def test_returns_non_empty_list(self):
        metrics = AgentStrategy().get_metrics()
        assert isinstance(metrics, list)
        assert len(metrics) > 0

    def test_all_entries_are_strings(self):
        metrics = AgentStrategy().get_metrics()
        assert all(isinstance(m, str) for m in metrics)

    def test_stable_across_calls(self):
        strategy = AgentStrategy()
        assert strategy.get_metrics() == strategy.get_metrics()

    def test_contains_expected_metric_names(self):
        metrics = AgentStrategy().get_metrics()
        assert metrics == ["tool_correctness", "task_completion", "bias", "toxicity"]

    def test_distinct_from_rag_strategy(self):
        assert set(AgentStrategy().get_metrics()) != set(RAGStrategy().get_metrics())

"""Unit tests for RAGStrategy (US2 — Metric Selection, FR-006)."""
from __future__ import annotations

from deepeval_platform.evaluation.strategies.rag_strategy import RAGStrategy
from deepeval_platform.evaluation.strategy_base import EvaluationStrategyBase


class TestRAGStrategy:
    def test_is_evaluation_strategy_base_subclass(self):
        assert issubclass(RAGStrategy, EvaluationStrategyBase)

    def test_returns_non_empty_list(self):
        metrics = RAGStrategy().get_metrics()
        assert isinstance(metrics, list)
        assert len(metrics) > 0

    def test_all_entries_are_strings(self):
        metrics = RAGStrategy().get_metrics()
        assert all(isinstance(m, str) for m in metrics)

    def test_stable_across_calls(self):
        strategy = RAGStrategy()
        assert strategy.get_metrics() == strategy.get_metrics()

    def test_contains_expected_metric_names(self):
        metrics = RAGStrategy().get_metrics()
        assert metrics == [
            "answer_relevancy",
            "faithfulness",
            "contextual_precision",
            "contextual_recall",
            "contextual_relevancy",
            "hallucination",
        ]

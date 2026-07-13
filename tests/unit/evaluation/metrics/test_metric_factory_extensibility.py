"""Unit test for MetricFactory's decorator-based self-registration extensibility (M3.1, US2).

Proves a brand-new metric can self-register and become instantiable by name through
MetricFactory with zero changes to any existing file (US2 AC1, SC-002) — the first
decorator-based self-registration pattern in this codebase (StrategyFactory's own
extensibility test, tests/unit/evaluation/test_strategy_factory_extensibility.py, covers a
different mechanism: a hardcoded dict subclassed/merged in the factory's own source).
"""
from __future__ import annotations

from unittest.mock import MagicMock

from deepeval_platform.evaluation import metrics  # noqa: F401 — triggers native wrapper registration
from deepeval_platform.evaluation.metrics.metric_base import MetricBase
from deepeval_platform.evaluation.metrics.metric_factory import MetricFactory


class _ThrowawayMetric(MetricBase):
    _native_metric_cls = MagicMock()


MetricFactory.register("custom_dummy_metric")(_ThrowawayMetric)


class TestMetricFactoryExtensibility:
    def test_throwaway_metric_registers_and_resolves_by_name(self):
        instance = MetricFactory.create(
            "custom_dummy_metric", threshold=0.8, deepeval_model=MagicMock()
        )
        assert isinstance(instance, _ThrowawayMetric)

    def test_real_us1_wrappers_remain_resolvable_and_unaffected(self):
        real_names = [
            "answer_relevancy",
            "faithfulness",
            "contextual_precision",
            "contextual_recall",
            "contextual_relevancy",
            "tool_correctness",
        ]
        for name in real_names:
            assert name in MetricFactory._registry
        assert "custom_dummy_metric" in MetricFactory._registry

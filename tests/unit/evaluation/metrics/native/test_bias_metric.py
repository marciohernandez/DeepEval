"""Unit tests for BiasMetricWrapper self-registration (M3.3, US2, FR-006)."""
from __future__ import annotations

from deepeval.metrics import BiasMetric

from deepeval_platform.evaluation.metrics.metric_base import MetricBase
from deepeval_platform.evaluation.metrics.metric_factory import MetricFactory
from deepeval_platform.evaluation.metrics.native.bias_metric import BiasMetricWrapper


class TestBiasMetricWrapper:
    def test_registered_under_canonical_name(self):
        assert MetricFactory._registry["bias"] is BiasMetricWrapper

    def test_wraps_native_bias_metric(self):
        assert BiasMetricWrapper._native_metric_cls is BiasMetric

    def test_is_metric_base_subclass(self):
        assert issubclass(BiasMetricWrapper, MetricBase)

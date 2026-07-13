"""Unit test for ContextualPrecisionMetricWrapper self-registration (M3.1, US1)."""
from __future__ import annotations

from deepeval.metrics import ContextualPrecisionMetric

from deepeval_platform.evaluation.metrics.metric_factory import MetricFactory
from deepeval_platform.evaluation.metrics.native.contextual_precision_metric import (
    ContextualPrecisionMetricWrapper,
)


class TestContextualPrecisionMetricWrapper:
    def test_registered_under_canonical_name(self):
        assert MetricFactory._registry["contextual_precision"] is ContextualPrecisionMetricWrapper

    def test_wraps_native_contextual_precision_metric(self):
        assert ContextualPrecisionMetricWrapper._native_metric_cls is ContextualPrecisionMetric

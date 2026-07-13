"""Unit test for ContextualRelevancyMetricWrapper self-registration (M3.1, US1)."""
from __future__ import annotations

from deepeval.metrics import ContextualRelevancyMetric

from deepeval_platform.evaluation.metrics.metric_factory import MetricFactory
from deepeval_platform.evaluation.metrics.native.contextual_relevancy_metric import (
    ContextualRelevancyMetricWrapper,
)


class TestContextualRelevancyMetricWrapper:
    def test_registered_under_canonical_name(self):
        assert MetricFactory._registry["contextual_relevancy"] is ContextualRelevancyMetricWrapper

    def test_wraps_native_contextual_relevancy_metric(self):
        assert ContextualRelevancyMetricWrapper._native_metric_cls is ContextualRelevancyMetric

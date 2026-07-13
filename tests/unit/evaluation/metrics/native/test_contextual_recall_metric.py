"""Unit test for ContextualRecallMetricWrapper self-registration (M3.1, US1)."""
from __future__ import annotations

from deepeval.metrics import ContextualRecallMetric

from deepeval_platform.evaluation.metrics.metric_factory import MetricFactory
from deepeval_platform.evaluation.metrics.native.contextual_recall_metric import (
    ContextualRecallMetricWrapper,
)


class TestContextualRecallMetricWrapper:
    def test_registered_under_canonical_name(self):
        assert MetricFactory._registry["contextual_recall"] is ContextualRecallMetricWrapper

    def test_wraps_native_contextual_recall_metric(self):
        assert ContextualRecallMetricWrapper._native_metric_cls is ContextualRecallMetric

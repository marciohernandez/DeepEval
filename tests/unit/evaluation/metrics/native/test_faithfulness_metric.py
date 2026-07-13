"""Unit test for FaithfulnessMetricWrapper self-registration (M3.1, US1)."""
from __future__ import annotations

from deepeval.metrics import FaithfulnessMetric

from deepeval_platform.evaluation.metrics.metric_factory import MetricFactory
from deepeval_platform.evaluation.metrics.native.faithfulness_metric import (
    FaithfulnessMetricWrapper,
)


class TestFaithfulnessMetricWrapper:
    def test_registered_under_canonical_name(self):
        assert MetricFactory._registry["faithfulness"] is FaithfulnessMetricWrapper

    def test_wraps_native_faithfulness_metric(self):
        assert FaithfulnessMetricWrapper._native_metric_cls is FaithfulnessMetric

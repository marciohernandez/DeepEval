"""Unit tests for ToxicityMetricWrapper self-registration (M3.3, US2, FR-006)."""
from __future__ import annotations

from deepeval.metrics import ToxicityMetric

from deepeval_platform.evaluation.metrics.metric_factory import MetricFactory
from deepeval_platform.evaluation.metrics.native.toxicity_metric import ToxicityMetricWrapper


class TestToxicityMetricWrapper:
    def test_registered_under_canonical_name(self):
        assert MetricFactory._registry["toxicity"] is ToxicityMetricWrapper

    def test_wraps_native_toxicity_metric(self):
        assert ToxicityMetricWrapper._native_metric_cls is ToxicityMetric

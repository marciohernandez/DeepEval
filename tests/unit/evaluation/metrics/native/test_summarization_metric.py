"""Unit tests for SummarizationMetricWrapper self-registration (M3.3, US4, FR-009)."""
from __future__ import annotations

from deepeval.metrics import SummarizationMetric

from deepeval_platform.evaluation.metrics.metric_factory import MetricFactory
from deepeval_platform.evaluation.metrics.native.summarization_metric import (
    SummarizationMetricWrapper,
)


class TestSummarizationMetricWrapper:
    def test_registered_under_canonical_name(self):
        assert MetricFactory._registry["summarization"] is SummarizationMetricWrapper

    def test_wraps_native_summarization_metric(self):
        assert SummarizationMetricWrapper._native_metric_cls is SummarizationMetric

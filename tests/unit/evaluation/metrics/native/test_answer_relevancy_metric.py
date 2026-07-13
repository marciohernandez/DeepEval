"""Unit test for AnswerRelevancyMetricWrapper self-registration (M3.1, US1)."""
from __future__ import annotations

from deepeval.metrics import AnswerRelevancyMetric

from deepeval_platform.evaluation.metrics.metric_factory import MetricFactory
from deepeval_platform.evaluation.metrics.native.answer_relevancy_metric import (
    AnswerRelevancyMetricWrapper,
)


class TestAnswerRelevancyMetricWrapper:
    def test_registered_under_canonical_name(self):
        assert MetricFactory._registry["answer_relevancy"] is AnswerRelevancyMetricWrapper

    def test_wraps_native_answer_relevancy_metric(self):
        assert AnswerRelevancyMetricWrapper._native_metric_cls is AnswerRelevancyMetric

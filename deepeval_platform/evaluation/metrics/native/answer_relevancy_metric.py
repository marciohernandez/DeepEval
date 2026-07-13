"""AnswerRelevancyMetricWrapper — self-registers under 'answer_relevancy' (M3.1, US1)."""
from __future__ import annotations

from deepeval.metrics import AnswerRelevancyMetric

from deepeval_platform.evaluation.metrics.metric_base import MetricBase
from deepeval_platform.evaluation.metrics.metric_factory import MetricFactory


@MetricFactory.register("answer_relevancy")
class AnswerRelevancyMetricWrapper(MetricBase):
    _native_metric_cls = AnswerRelevancyMetric

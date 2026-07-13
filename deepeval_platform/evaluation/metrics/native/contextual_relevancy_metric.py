"""ContextualRelevancyMetricWrapper — self-registers under 'contextual_relevancy' (M3.1, US1)."""
from __future__ import annotations

from deepeval.metrics import ContextualRelevancyMetric

from deepeval_platform.evaluation.metrics.metric_base import MetricBase
from deepeval_platform.evaluation.metrics.metric_factory import MetricFactory


@MetricFactory.register("contextual_relevancy")
class ContextualRelevancyMetricWrapper(MetricBase):
    _native_metric_cls = ContextualRelevancyMetric

"""ContextualRecallMetricWrapper — self-registers under 'contextual_recall' (M3.1, US1)."""
from __future__ import annotations

from deepeval.metrics import ContextualRecallMetric

from deepeval_platform.evaluation.metrics.metric_base import MetricBase
from deepeval_platform.evaluation.metrics.metric_factory import MetricFactory


@MetricFactory.register("contextual_recall")
class ContextualRecallMetricWrapper(MetricBase):
    _native_metric_cls = ContextualRecallMetric

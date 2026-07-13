"""ContextualPrecisionMetricWrapper — self-registers under 'contextual_precision' (M3.1, US1)."""
from __future__ import annotations

from deepeval.metrics import ContextualPrecisionMetric

from deepeval_platform.evaluation.metrics.metric_base import MetricBase
from deepeval_platform.evaluation.metrics.metric_factory import MetricFactory


@MetricFactory.register("contextual_precision")
class ContextualPrecisionMetricWrapper(MetricBase):
    _native_metric_cls = ContextualPrecisionMetric

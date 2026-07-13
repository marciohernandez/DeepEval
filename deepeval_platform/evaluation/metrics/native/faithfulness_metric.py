"""FaithfulnessMetricWrapper — self-registers under 'faithfulness' (M3.1, US1)."""
from __future__ import annotations

from deepeval.metrics import FaithfulnessMetric

from deepeval_platform.evaluation.metrics.metric_base import MetricBase
from deepeval_platform.evaluation.metrics.metric_factory import MetricFactory


@MetricFactory.register("faithfulness")
class FaithfulnessMetricWrapper(MetricBase):
    _native_metric_cls = FaithfulnessMetric

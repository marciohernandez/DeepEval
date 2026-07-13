"""ToolCorrectnessMetricWrapper — self-registers under 'tool_correctness' (M3.1, US1)."""
from __future__ import annotations

from deepeval.metrics import ToolCorrectnessMetric

from deepeval_platform.evaluation.metrics.metric_base import MetricBase
from deepeval_platform.evaluation.metrics.metric_factory import MetricFactory


@MetricFactory.register("tool_correctness")
class ToolCorrectnessMetricWrapper(MetricBase):
    _native_metric_cls = ToolCorrectnessMetric

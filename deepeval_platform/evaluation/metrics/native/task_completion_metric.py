"""TaskCompletionMetricWrapper — self-registers under 'task_completion' (M3.2, US1)."""
from __future__ import annotations

from deepeval.metrics import TaskCompletionMetric

from deepeval_platform.evaluation.metrics.metric_base import MetricBase
from deepeval_platform.evaluation.metrics.metric_factory import MetricFactory


@MetricFactory.register("task_completion")
class TaskCompletionMetricWrapper(MetricBase):
    _native_metric_cls = TaskCompletionMetric

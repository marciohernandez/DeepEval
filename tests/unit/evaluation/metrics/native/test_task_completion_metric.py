"""Unit test for TaskCompletionMetricWrapper self-registration (M3.2, US1)."""
from __future__ import annotations

from deepeval.metrics import TaskCompletionMetric

from deepeval_platform.evaluation.metrics.metric_factory import MetricFactory
from deepeval_platform.evaluation.metrics.native.task_completion_metric import (
    TaskCompletionMetricWrapper,
)


class TestTaskCompletionMetricWrapper:
    def test_registered_under_canonical_name(self):
        assert MetricFactory._registry["task_completion"] is TaskCompletionMetricWrapper

    def test_wraps_native_task_completion_metric(self):
        assert TaskCompletionMetricWrapper._native_metric_cls is TaskCompletionMetric

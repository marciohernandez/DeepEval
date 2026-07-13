"""Unit test for ToolCorrectnessMetricWrapper self-registration (M3.1, US1)."""
from __future__ import annotations

from deepeval.metrics import ToolCorrectnessMetric

from deepeval_platform.evaluation.metrics.metric_factory import MetricFactory
from deepeval_platform.evaluation.metrics.native.tool_correctness_metric import (
    ToolCorrectnessMetricWrapper,
)


class TestToolCorrectnessMetricWrapper:
    def test_registered_under_canonical_name(self):
        assert MetricFactory._registry["tool_correctness"] is ToolCorrectnessMetricWrapper

    def test_wraps_native_tool_correctness_metric(self):
        assert ToolCorrectnessMetricWrapper._native_metric_cls is ToolCorrectnessMetric

"""BiasMetricWrapper — self-registers under 'bias' (M3.3, US2, FR-006).

No _build_test_case override needed — operates on input/actual_output, already populated by
MetricBase._build_test_case.
"""
from __future__ import annotations

from deepeval.metrics import BiasMetric

from deepeval_platform.evaluation.metrics.metric_base import MetricBase
from deepeval_platform.evaluation.metrics.metric_factory import MetricFactory


@MetricFactory.register("bias")
class BiasMetricWrapper(MetricBase):
    _native_metric_cls = BiasMetric

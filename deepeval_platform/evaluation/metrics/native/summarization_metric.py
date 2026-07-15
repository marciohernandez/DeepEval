"""SummarizationMetricWrapper — self-registers under 'summarization' (M3.3, US4, FR-009).

No __init__ override, no extra kwargs — n/assessment_questions stay at native defaults
(research.md §R1).
"""
from __future__ import annotations

from deepeval.metrics import SummarizationMetric

from deepeval_platform.evaluation.metrics.metric_base import MetricBase
from deepeval_platform.evaluation.metrics.metric_factory import MetricFactory


@MetricFactory.register("summarization")
class SummarizationMetricWrapper(MetricBase):
    _native_metric_cls = SummarizationMetric

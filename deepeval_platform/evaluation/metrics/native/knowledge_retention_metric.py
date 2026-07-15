"""KnowledgeRetentionMetricWrapper — self-registers under 'knowledge_retention' (M3.3, US3, FR-008)."""
from __future__ import annotations

from deepeval.metrics import KnowledgeRetentionMetric

from deepeval_platform.evaluation.metrics.conversational_metric_base import (
    ConversationalMetricBase,
)
from deepeval_platform.evaluation.metrics.metric_factory import MetricFactory


@MetricFactory.register("knowledge_retention")
class KnowledgeRetentionMetricWrapper(ConversationalMetricBase):
    _native_metric_cls = KnowledgeRetentionMetric

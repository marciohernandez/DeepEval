"""ConversationCompletenessMetricWrapper — self-registers under 'conversation_completeness'
(M3.3, US1, FR-007). Closes the name ConversationStrategy.get_metrics() has declared since M2.1
but never resolved.
"""
from __future__ import annotations

from deepeval.metrics import ConversationCompletenessMetric

from deepeval_platform.evaluation.metrics.conversational_metric_base import (
    ConversationalMetricBase,
)
from deepeval_platform.evaluation.metrics.metric_factory import MetricFactory


@MetricFactory.register("conversation_completeness")
class ConversationCompletenessMetricWrapper(ConversationalMetricBase):
    _native_metric_cls = ConversationCompletenessMetric

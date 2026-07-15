"""ConversationRelevancyMetricWrapper — self-registers under 'turn_relevancy' (M3.3, US1, FR-005).

Wraps DeepEval's TurnRelevancyMetric — there is no native class literally named
"ConversationRelevancyMetric" — under the canonical name ConversationStrategy.get_metrics()
already declares.
"""
from __future__ import annotations

from deepeval.metrics import TurnRelevancyMetric

from deepeval_platform.evaluation.metrics.conversational_metric_base import (
    ConversationalMetricBase,
)
from deepeval_platform.evaluation.metrics.metric_factory import MetricFactory


@MetricFactory.register("turn_relevancy")
class ConversationRelevancyMetricWrapper(ConversationalMetricBase):
    _native_metric_cls = TurnRelevancyMetric

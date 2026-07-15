"""Unit tests for ConversationRelevancyMetricWrapper self-registration (M3.3, US1, FR-005).

Wraps DeepEval's TurnRelevancyMetric — there is no native class literally named
"ConversationRelevancyMetric" (research.md §R1) — and registers under the canonical name
"turn_relevancy", matching what ConversationStrategy.get_metrics() already declares.
"""
from __future__ import annotations

from deepeval.metrics import TurnRelevancyMetric

from deepeval_platform.evaluation.metrics.metric_factory import MetricFactory
from deepeval_platform.evaluation.metrics.native.conversation_relevancy_metric import (
    ConversationRelevancyMetricWrapper,
)


class TestConversationRelevancyMetricWrapper:
    def test_registered_under_canonical_name(self):
        assert MetricFactory._registry["turn_relevancy"] is ConversationRelevancyMetricWrapper

    def test_wraps_native_turn_relevancy_metric(self):
        assert ConversationRelevancyMetricWrapper._native_metric_cls is TurnRelevancyMetric

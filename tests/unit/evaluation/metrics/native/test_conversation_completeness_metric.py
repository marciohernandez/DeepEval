"""Unit tests for ConversationCompletenessMetricWrapper self-registration (M3.3, US1, FR-007)."""
from __future__ import annotations

from deepeval.metrics import ConversationCompletenessMetric

from deepeval_platform.evaluation.metrics.conversational_metric_base import (
    ConversationalMetricBase,
)
from deepeval_platform.evaluation.metrics.metric_factory import MetricFactory
from deepeval_platform.evaluation.metrics.native.conversation_completeness_metric import (
    ConversationCompletenessMetricWrapper,
)


class TestConversationCompletenessMetricWrapper:
    def test_registered_under_canonical_name(self):
        assert (
            MetricFactory._registry["conversation_completeness"]
            is ConversationCompletenessMetricWrapper
        )

    def test_wraps_native_conversation_completeness_metric(self):
        assert (
            ConversationCompletenessMetricWrapper._native_metric_cls
            is ConversationCompletenessMetric
        )

    def test_is_conversational_metric_base_subclass(self):
        assert issubclass(ConversationCompletenessMetricWrapper, ConversationalMetricBase)

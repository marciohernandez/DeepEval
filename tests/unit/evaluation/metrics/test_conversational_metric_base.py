"""Unit tests for ConversationalMetricBase (M3.3 Foundational, FR-002/FR-003, data-model.md).

Mirrors test_metric_base.py's pattern for MetricBase — a concrete dummy subclass wraps a mocked
native BaseConversationalMetric so no real DeepEval scoring runs.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import ValidationError

from deepeval_platform.evaluation.evaluation_context import EvaluationContext
from deepeval_platform.evaluation.metrics.conversational_metric_base import (
    ConversationalMetricBase,
)
from deepeval_platform.normalization.models import Message, NormalizedTrace


class _DummyNativeConversational:
    def __init__(self, threshold: float = 0.5, model=None, async_mode=True):
        self.threshold = threshold
        self.success = None
        self.score = None
        self.a_measure = AsyncMock()


class _DummyConversationalMetric(ConversationalMetricBase):
    _native_metric_cls = _DummyNativeConversational


class TestConversationalMetricBaseMeasure:
    async def test_measure_builds_conversational_test_case_and_returns_metric_result(self):
        metric = _DummyConversationalMetric(threshold=0.5, deepeval_model=MagicMock())
        metric._native.score = 0.9
        metric._native.success = True

        trace = NormalizedTrace(
            messages=[
                Message(role="user", content="Hi"),
                Message(role="assistant", content="Hello, how can I help?"),
            ]
        )
        context = EvaluationContext(trace=trace, thresholds={})

        result = await metric.measure(context)

        metric._native.a_measure.assert_awaited_once()
        call_args = metric._native.a_measure.call_args
        test_case = call_args.args[0]
        assert [t.role for t in test_case.turns] == ["user", "assistant"]
        assert [t.content for t in test_case.turns] == ["Hi", "Hello, how can I help?"]
        assert call_args.kwargs["_show_indicator"] is False

        assert result.score == 0.9
        assert result.passed is True

    async def test_chatbot_role_forwarded_when_given(self):
        metric = _DummyConversationalMetric(threshold=0.5, deepeval_model=MagicMock())
        test_case = metric._build_test_case(
            NormalizedTrace(messages=[Message(role="user", content="Hi")]),
            chatbot_role="A polite assistant",
        )
        assert test_case.chatbot_role == "A polite assistant"

    def test_threshold_and_passed_proxy_native(self):
        metric = _DummyConversationalMetric(threshold=0.7, deepeval_model=MagicMock())
        metric._native.success = False
        assert metric.threshold == 0.7
        assert metric.passed is False

    def test_invalid_role_raises_validation_error_uncaught(self):
        trace = NormalizedTrace(messages=[Message(role="system", content="You are a bot")])
        with pytest.raises(ValidationError):
            _DummyConversationalMetric._build_test_case(trace)

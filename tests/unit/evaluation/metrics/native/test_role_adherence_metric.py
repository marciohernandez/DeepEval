"""Unit tests for RoleAdherenceMetricWrapper self-registration (M3.3, US3, FR-008/FR-010a)."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from deepeval.metrics import RoleAdherenceMetric
from deepeval.models.base_model import DeepEvalBaseLLM

from deepeval_platform.evaluation.evaluation_context import EvaluationContext
from deepeval_platform.evaluation.metrics.metric_factory import MetricFactory
from deepeval_platform.evaluation.metrics.native.role_adherence_metric import (
    RoleAdherenceMetricWrapper,
)
from deepeval_platform.normalization.models import Message, NormalizedTrace


class TestRoleAdherenceMetricWrapper:
    def test_registered_under_canonical_name(self):
        assert MetricFactory._registry["role_adherence"] is RoleAdherenceMetricWrapper

    def test_wraps_native_role_adherence_metric(self):
        assert RoleAdherenceMetricWrapper._native_metric_cls is RoleAdherenceMetric

    async def test_chatbot_role_forwarded_to_test_case(self):
        metric = RoleAdherenceMetricWrapper(
            threshold=0.5,
            deepeval_model=MagicMock(spec=DeepEvalBaseLLM),
            chatbot_role="A polite banking assistant",
        )
        metric._native.a_measure = AsyncMock()
        trace = NormalizedTrace(
            messages=[Message(role="user", content="Hi"), Message(role="assistant", content="Hello!")]
        )
        context = EvaluationContext(trace=trace, thresholds={})

        await metric.measure(context)

        test_case = metric._native.a_measure.call_args.args[0]
        assert test_case.chatbot_role == "A polite banking assistant"

    async def test_missing_chatbot_role_defaults_to_none(self):
        metric = RoleAdherenceMetricWrapper(
            threshold=0.5, deepeval_model=MagicMock(spec=DeepEvalBaseLLM)
        )
        metric._native.a_measure = AsyncMock()
        trace = NormalizedTrace(
            messages=[Message(role="user", content="Hi"), Message(role="assistant", content="Hello!")]
        )
        context = EvaluationContext(trace=trace, thresholds={})

        await metric.measure(context)

        test_case = metric._native.a_measure.call_args.args[0]
        assert test_case.chatbot_role is None

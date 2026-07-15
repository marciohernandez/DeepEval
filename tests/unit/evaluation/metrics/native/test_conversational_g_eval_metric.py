"""Unit tests for ConversationalGEvalMetricWrapper self-registration (M3.3, US4, FR-010).

`name` is a fixed literal inside the wrapper's __init__ — data-model.md notes it is not
bot-configurable this milestone; only `criteria` comes from bots.yaml.
"""
from __future__ import annotations

from unittest.mock import MagicMock

from deepeval.metrics import ConversationalGEval
from deepeval.models.base_model import DeepEvalBaseLLM

from deepeval_platform.evaluation.metrics.conversational_metric_base import (
    ConversationalMetricBase,
)
from deepeval_platform.evaluation.metrics.metric_factory import MetricFactory
from deepeval_platform.evaluation.metrics.native.conversational_g_eval_metric import (
    ConversationalGEvalMetricWrapper,
)


class TestConversationalGEvalMetricWrapper:
    def test_registered_under_canonical_name(self):
        assert MetricFactory._registry["conversational_g_eval"] is ConversationalGEvalMetricWrapper

    def test_wraps_native_conversational_g_eval(self):
        assert ConversationalGEvalMetricWrapper._native_metric_cls is ConversationalGEval

    def test_is_conversational_metric_base_subclass(self):
        assert issubclass(ConversationalGEvalMetricWrapper, ConversationalMetricBase)

    def test_criteria_forwarded_to_native_constructor(self):
        metric = ConversationalGEvalMetricWrapper(
            threshold=0.5,
            deepeval_model=MagicMock(spec=DeepEvalBaseLLM),
            criteria="Stays on-topic",
        )
        assert metric._native.criteria == "Stays on-topic"
        assert metric._native.name

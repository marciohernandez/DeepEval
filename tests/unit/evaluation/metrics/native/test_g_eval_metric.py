"""Unit tests for GEvalMetricWrapper self-registration (M3.4, US1, FR-001/FR-002).

`evaluation_params` is fixed at construction — native `GEval.measure()`/`a_measure()` raise
`ValueError` when it is falsy (research.md §R1); `name` is a fixed literal, matching
`ConversationalGEvalMetricWrapper`'s precedent (M3.3).
"""
from __future__ import annotations

from unittest.mock import MagicMock

from deepeval.metrics import GEval
from deepeval.models.base_model import DeepEvalBaseLLM
from deepeval.test_case import SingleTurnParams

from deepeval_platform.evaluation.metrics.metric_base import MetricBase
from deepeval_platform.evaluation.metrics.metric_factory import MetricFactory
from deepeval_platform.evaluation.metrics.native.g_eval_metric import GEvalMetricWrapper


class TestGEvalMetricWrapper:
    def test_registered_under_canonical_name(self):
        assert MetricFactory._registry["g_eval"] is GEvalMetricWrapper

    def test_wraps_native_g_eval(self):
        assert GEvalMetricWrapper._native_metric_cls is GEval

    def test_is_metric_base_subclass(self):
        assert issubclass(GEvalMetricWrapper, MetricBase)

    def test_criteria_and_fixed_evaluation_params_forwarded_to_native_constructor(self):
        metric = GEvalMetricWrapper(
            threshold=0.5,
            deepeval_model=MagicMock(spec=DeepEvalBaseLLM),
            criteria="Response must stay formal and never promise a delivery date",
        )
        assert (
            metric._native.criteria
            == "Response must stay formal and never promise a delivery date"
        )
        assert metric._native.name
        assert metric._native.evaluation_params == [
            SingleTurnParams.INPUT,
            SingleTurnParams.ACTUAL_OUTPUT,
        ]

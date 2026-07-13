"""Unit tests for MetricBase (M3.1, data-model.md, research.md §7/§8)."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from deepeval_platform.evaluation.evaluation_context import EvaluationContext
from deepeval_platform.evaluation.metrics.metric_base import MetricBase
from deepeval_platform.normalization.models import NormalizedTrace
from deepeval_platform.normalization.models import ToolCall as ProjectToolCall


@pytest.fixture
def mock_native_instance():
    instance = MagicMock()
    instance.score = 0.9
    instance.threshold = 0.8
    instance.success = True
    instance.reason = "looks good"
    instance.a_measure = AsyncMock(return_value=0.9)
    return instance


@pytest.fixture
def mock_native_cls(mock_native_instance):
    return MagicMock(return_value=mock_native_instance)


@pytest.fixture
def metric_cls(mock_native_cls):
    class _TestMetric(MetricBase):
        _native_metric_cls = mock_native_cls

    return _TestMetric


class TestMetricBaseConstruction:
    def test_constructs_native_metric_with_threshold_and_model(self, metric_cls, mock_native_cls):
        deepeval_model = MagicMock()
        metric_cls(threshold=0.8, deepeval_model=deepeval_model)
        mock_native_cls.assert_called_once_with(threshold=0.8, model=deepeval_model, async_mode=True)


class TestMetricBaseProperties:
    def test_threshold_proxies_native(self, metric_cls, mock_native_instance):
        metric = metric_cls(threshold=0.8, deepeval_model=MagicMock())
        assert metric.threshold == mock_native_instance.threshold

    def test_passed_proxies_native(self, metric_cls, mock_native_instance):
        metric = metric_cls(threshold=0.8, deepeval_model=MagicMock())
        assert metric.passed == mock_native_instance.success


class TestMetricBaseMeasure:
    async def test_builds_llm_test_case_from_trace(self, metric_cls, mock_native_instance):
        metric = metric_cls(threshold=0.8, deepeval_model=MagicMock())
        trace = NormalizedTrace(
            input="What is the refund policy?",
            output="Refunds within 30 days.",
            expected_output="Refunds within 30 days of purchase.",
            context=["ctx1", "ctx2"],
            tools_called=[
                ProjectToolCall(name="search", input_parameters={"q": "refund"}, output="result")
            ],
        )
        context = EvaluationContext(trace=trace, thresholds={"faithfulness": 0.8})

        await metric.measure(context)

        mock_native_instance.a_measure.assert_awaited_once()
        call_args = mock_native_instance.a_measure.call_args
        test_case = call_args.args[0]
        assert test_case.input == "What is the refund policy?"
        assert test_case.actual_output == "Refunds within 30 days."
        assert test_case.expected_output == "Refunds within 30 days of purchase."
        assert test_case.retrieval_context == ["ctx1", "ctx2"]
        assert len(test_case.tools_called) == 1
        assert test_case.tools_called[0].name == "search"
        assert test_case.tools_called[0].input_parameters == {"q": "refund"}
        assert test_case.tools_called[0].output == "result"
        assert call_args.kwargs == {"_show_indicator": False}

    async def test_returns_metric_result_wrapping_native_state(self, metric_cls, mock_native_instance):
        metric = metric_cls(threshold=0.8, deepeval_model=MagicMock())
        trace = NormalizedTrace(input="q", output="a")
        context = EvaluationContext(trace=trace, thresholds={})

        result = await metric.measure(context)

        assert result.score == mock_native_instance.score
        assert result.threshold == mock_native_instance.threshold
        assert result.passed == mock_native_instance.success
        assert result.error is None

    async def test_native_exception_propagates_uncaught(self, metric_cls, mock_native_instance):
        mock_native_instance.a_measure = AsyncMock(side_effect=ValueError("boom"))
        metric = metric_cls(threshold=0.8, deepeval_model=MagicMock())
        trace = NormalizedTrace(input="q", output="a")
        context = EvaluationContext(trace=trace, thresholds={})

        with pytest.raises(ValueError, match="boom"):
            await metric.measure(context)

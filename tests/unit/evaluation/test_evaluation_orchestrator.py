"""Unit tests for EvaluationOrchestrator (M3.1, US1 + US3) — core flow + robustness edge cases.

Mocks MetricFactory/LLMProviderFactory/ConfigManager (injected); no network access.
"""
from __future__ import annotations

import asyncio
import inspect
from unittest.mock import AsyncMock, MagicMock

import pytest

from deepeval_platform.evaluation.errors import (
    ConfigResolutionError,
    DuplicateMetricRequestError,
    EmptyMetricListError,
    InvalidThresholdError,
)
from deepeval_platform.evaluation.evaluation_orchestrator import EvaluationOrchestrator
from deepeval_platform.evaluation.evaluation_result import MetricResult
from deepeval_platform.normalization.models import NormalizedTrace


class _FakeNativeAnswerRelevancy:
    def __init__(self, threshold: float = 0.5, model=None, async_mode=True):
        pass


class _FakeNativeFaithfulness:
    def __init__(self, threshold: float = 0.5, model=None, async_mode=True):
        pass


class _FakeAnswerRelevancyWrapper:
    _native_metric_cls = _FakeNativeAnswerRelevancy


class _FakeFaithfulnessWrapper:
    _native_metric_cls = _FakeNativeFaithfulness


@pytest.fixture
def fake_registry():
    return {
        "answer_relevancy": _FakeAnswerRelevancyWrapper,
        "faithfulness": _FakeFaithfulnessWrapper,
    }


@pytest.fixture
def mock_metric_factory(mocker, fake_registry):
    factory = mocker.patch("deepeval_platform.evaluation.evaluation_orchestrator.MetricFactory")
    factory._registry = fake_registry

    def default_create(name, *, threshold, deepeval_model):
        instance = MagicMock()
        instance.measure = AsyncMock(
            return_value=MetricResult(score=0.9, threshold=threshold, passed=True, error=None)
        )
        return instance

    factory.create.side_effect = default_create
    return factory


@pytest.fixture
def mock_llm_provider_factory(mocker):
    factory = mocker.patch("deepeval_platform.evaluation.evaluation_orchestrator.LLMProviderFactory")
    provider = MagicMock()
    provider.as_deepeval_model.return_value = MagicMock(name="fake_judge")
    factory.create.return_value = provider
    return factory


@pytest.fixture
def stub_config():
    """ConfigManager stub with no bot-specific thresholds configured (native defaults apply)."""
    config = MagicMock()
    values = {
        "evaluation.metric_timeout_seconds": "30",
        "evaluation.llm_judge.provider": "openai",
        "evaluation.llm_judge.model": "gpt-4o",
    }
    config.get_optional.side_effect = lambda key, default="": values.get(key, default)
    config.get.side_effect = lambda key: values[key]
    return config


@pytest.fixture
def orchestrator(stub_config, mock_metric_factory, mock_llm_provider_factory):
    return EvaluationOrchestrator(config=stub_config)


@pytest.fixture
def trace():
    return NormalizedTrace(
        input="What is the refund policy?",
        output="Refunds within 30 days.",
        context=["Our policy allows returns within 30 days."],
    )


class TestEvaluateReturnsPerMetricResults:
    async def test_evaluate_returns_per_metric_results(self, orchestrator, trace):
        result = await orchestrator.evaluate(
            trace=trace, bot_id="test_rag_bot", metric_names=["answer_relevancy", "faithfulness"]
        )
        assert set(result.metrics.keys()) == {"answer_relevancy", "faithfulness"}
        assert result.metrics["answer_relevancy"].score == 0.9
        assert result.metrics["faithfulness"].score == 0.9
        assert result.passed is True


class TestMetricExceptionIsolated:
    async def test_metric_exception_isolated(
        self, stub_config, mock_metric_factory, mock_llm_provider_factory, trace
    ):
        def create(name, *, threshold, deepeval_model):
            instance = MagicMock()
            if name == "faithfulness":
                instance.measure = AsyncMock(side_effect=ValueError("boom"))
            else:
                instance.measure = AsyncMock(
                    return_value=MetricResult(score=0.9, threshold=threshold, passed=True, error=None)
                )
            return instance

        mock_metric_factory.create.side_effect = create
        orchestrator = EvaluationOrchestrator(config=stub_config)

        result = await orchestrator.evaluate(
            trace=trace, bot_id="test_rag_bot", metric_names=["answer_relevancy", "faithfulness"]
        )

        assert result.metrics["answer_relevancy"].passed is True
        failed = result.metrics["faithfulness"]
        assert failed.score is None
        assert failed.passed is False
        assert failed.error is not None
        assert result.passed is False


class TestMetricTimeoutIsolatedNoRetry:
    async def test_metric_timeout_isolated_no_retry(
        self, stub_config, mock_metric_factory, mock_llm_provider_factory, trace
    ):
        values = {
            "evaluation.metric_timeout_seconds": "30",
            "evaluation.metric_timeout_overrides.faithfulness": "0.05",
            "evaluation.llm_judge.provider": "openai",
            "evaluation.llm_judge.model": "gpt-4o",
        }
        stub_config.get_optional.side_effect = lambda key, default="": values.get(key, default)

        call_count = {"faithfulness": 0}

        def create(name, *, threshold, deepeval_model):
            instance = MagicMock()
            if name == "faithfulness":
                async def slow_measure(context):
                    call_count["faithfulness"] += 1
                    await asyncio.sleep(1)
                    return MetricResult(score=0.9, threshold=threshold, passed=True, error=None)

                instance.measure = slow_measure
            else:
                instance.measure = AsyncMock(
                    return_value=MetricResult(score=0.9, threshold=threshold, passed=True, error=None)
                )
            return instance

        mock_metric_factory.create.side_effect = create
        orchestrator = EvaluationOrchestrator(config=stub_config)

        result = await orchestrator.evaluate(
            trace=trace, bot_id="test_rag_bot", metric_names=["answer_relevancy", "faithfulness"]
        )

        failed = result.metrics["faithfulness"]
        assert failed.score is None
        assert failed.passed is False
        assert failed.error is not None
        assert call_count["faithfulness"] == 1
        assert result.metrics["answer_relevancy"].passed is True


class TestEmptyMetricListRejected:
    async def test_empty_metric_list_rejected(self, orchestrator, trace, mocker):
        context_spy = mocker.patch(
            "deepeval_platform.evaluation.evaluation_orchestrator.EvaluationContext"
        )
        with pytest.raises(EmptyMetricListError):
            await orchestrator.evaluate(trace=trace, bot_id="test_rag_bot", metric_names=[])
        context_spy.assert_not_called()


class TestDuplicateMetricNamesRejected:
    async def test_duplicate_metric_names_rejected(self, orchestrator, trace):
        with pytest.raises(DuplicateMetricRequestError) as exc_info:
            await orchestrator.evaluate(
                trace=trace,
                bot_id="test_rag_bot",
                metric_names=["faithfulness", "faithfulness"],
            )
        assert "faithfulness" in exc_info.value.duplicates


class TestInvalidThresholdAbortsBeforeAnyMeasure:
    async def test_invalid_threshold_aborts_before_any_measure(
        self, stub_config, mock_metric_factory, mock_llm_provider_factory, trace
    ):
        values = {
            "bots.test_rag_bot.metrics.faithfulness.threshold": "1.5",
            "evaluation.metric_timeout_seconds": "30",
            "evaluation.llm_judge.provider": "openai",
            "evaluation.llm_judge.model": "gpt-4o",
        }
        stub_config.get_optional.side_effect = lambda key, default="": values.get(key, default)
        orchestrator = EvaluationOrchestrator(config=stub_config)

        with pytest.raises(InvalidThresholdError) as exc_info:
            await orchestrator.evaluate(
                trace=trace, bot_id="test_rag_bot", metric_names=["faithfulness"]
            )
        assert any(name == "faithfulness" for name, _ in exc_info.value.offending)
        mock_metric_factory.create.assert_not_called()


class TestConfigManagerFailureAborts:
    async def test_config_manager_failure_aborts(
        self, stub_config, mock_metric_factory, mock_llm_provider_factory, trace
    ):
        def raising_get_optional(key, default=""):
            raise RuntimeError("malformed yaml")

        stub_config.get_optional.side_effect = raising_get_optional
        orchestrator = EvaluationOrchestrator(config=stub_config)

        with pytest.raises(ConfigResolutionError) as exc_info:
            await orchestrator.evaluate(
                trace=trace, bot_id="test_rag_bot", metric_names=["faithfulness"]
            )
        assert exc_info.value.bot_id == "test_rag_bot"
        mock_metric_factory.create.assert_not_called()


class TestConfiguredThresholdApplied:
    async def test_configured_threshold_applied(
        self, stub_config, mock_metric_factory, mock_llm_provider_factory, trace
    ):
        values = {
            "bots.test_rag_bot.metrics.faithfulness.threshold": "0.8",
            "evaluation.metric_timeout_seconds": "30",
            "evaluation.llm_judge.provider": "openai",
            "evaluation.llm_judge.model": "gpt-4o",
        }
        stub_config.get_optional.side_effect = lambda key, default="": values.get(key, default)
        orchestrator = EvaluationOrchestrator(config=stub_config)

        result = await orchestrator.evaluate(
            trace=trace, bot_id="test_rag_bot", metric_names=["faithfulness"]
        )

        mock_metric_factory.create.assert_called_once()
        _, kwargs = mock_metric_factory.create.call_args
        assert kwargs["threshold"] == 0.8
        assert result.metrics["faithfulness"].threshold == 0.8


class TestMissingConfigUsesNativeDefault:
    async def test_missing_config_uses_native_default(self, orchestrator, trace):
        # stub_config has no bots.test_rag_bot.metrics.faithfulness.threshold entry configured
        result = await orchestrator.evaluate(
            trace=trace, bot_id="test_rag_bot", metric_names=["faithfulness"]
        )

        native_default = inspect.signature(
            _FakeNativeFaithfulness.__init__
        ).parameters["threshold"].default
        assert result.metrics["faithfulness"].threshold == native_default


class TestUnknownBotIdUsesNativeDefaults:
    async def test_unknown_bot_id_uses_native_defaults(self, orchestrator, trace):
        result = await orchestrator.evaluate(
            trace=trace, bot_id="totally_unknown_bot", metric_names=["answer_relevancy", "faithfulness"]
        )

        assert result.passed is True
        native_default = inspect.signature(
            _FakeNativeAnswerRelevancy.__init__
        ).parameters["threshold"].default
        assert result.metrics["answer_relevancy"].threshold == native_default

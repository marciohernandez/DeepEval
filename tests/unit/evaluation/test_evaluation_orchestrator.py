"""Unit tests for EvaluationOrchestrator (M3.1, US1 + US3) — core flow + robustness edge cases.

Mocks MetricFactory/LLMProviderFactory/ConfigManager (injected); no network access.
"""
from __future__ import annotations

import asyncio
import inspect
from unittest.mock import AsyncMock, MagicMock

import pytest

from deepeval.errors import MissingTestCaseParamsError
from deepeval.test_case import Turn
from pydantic import ValidationError

from deepeval_platform.evaluation.errors import (
    ConfigResolutionError,
    DuplicateMetricRequestError,
    EmptyMetricListError,
    InvalidThresholdError,
)
from deepeval_platform.evaluation.evaluation_orchestrator import EvaluationOrchestrator
from deepeval_platform.evaluation.evaluation_result import MetricResult
from deepeval_platform.normalization.models import Message, NormalizedTrace


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


class TestResolvedOptionsForwardedToMetricFactory:
    async def test_resolved_options_forwarded_to_metric_factory(
        self, stub_config, mock_metric_factory, mock_llm_provider_factory, trace
    ):
        captured_kwargs: dict[str, dict] = {}

        def create(name, *, threshold, deepeval_model, **options):
            captured_kwargs[name] = options
            instance = MagicMock()
            instance.measure = AsyncMock(
                return_value=MetricResult(score=0.9, threshold=threshold, passed=True, error=None)
            )
            return instance

        mock_metric_factory.create.side_effect = create

        resolver = MagicMock()

        def resolve_options(bot_id, names):
            name = names[0]
            if name == "faithfulness":
                return {"faithfulness": {"extra": "value"}}
            return {name: {}}

        resolver.resolve_options.side_effect = resolve_options

        orchestrator = EvaluationOrchestrator(config=stub_config, resolver=resolver)

        await orchestrator.evaluate(
            trace=trace, bot_id="test_rag_bot", metric_names=["answer_relevancy", "faithfulness"]
        )

        assert captured_kwargs["faithfulness"] == {"extra": "value"}
        assert captured_kwargs["answer_relevancy"] == {}


class TestNoConfiguredOptionsMatchesPriorBehavior:
    async def test_no_configured_options_matches_byte_identical_prior_behavior(
        self, stub_config, mock_metric_factory, mock_llm_provider_factory, trace
    ):
        resolver = MagicMock()
        resolver.resolve_options.side_effect = lambda bot_id, names: {names[0]: {}}

        orchestrator = EvaluationOrchestrator(config=stub_config, resolver=resolver)

        result = await orchestrator.evaluate(
            trace=trace, bot_id="test_rag_bot", metric_names=["answer_relevancy", "faithfulness"]
        )

        assert set(result.metrics.keys()) == {"answer_relevancy", "faithfulness"}
        assert result.metrics["answer_relevancy"].score == 0.9
        assert result.metrics["faithfulness"].score == 0.9
        assert result.passed is True


class TestRoleAdherenceMissingChatbotRoleIsolatedNotSkipped:
    async def test_role_adherence_missing_chatbot_role_isolated_not_skipped(
        self, stub_config, mock_metric_factory, mock_llm_provider_factory, trace
    ):
        class _FakeNativeRoleAdherence:
            def __init__(self, threshold: float = 0.5, model=None, async_mode=True):
                pass

        class _FakeRoleAdherenceWrapper:
            _native_metric_cls = _FakeNativeRoleAdherence

        class _FakeNativeBias:
            def __init__(self, threshold: float = 0.5, model=None, async_mode=True):
                pass

        class _FakeBiasWrapper:
            _native_metric_cls = _FakeNativeBias

        mock_metric_factory._registry = {
            "role_adherence": _FakeRoleAdherenceWrapper,
            "bias": _FakeBiasWrapper,
        }

        def create(name, *, threshold, deepeval_model, **options):
            instance = MagicMock()
            if name == "role_adherence":
                instance.measure = AsyncMock(
                    side_effect=MissingTestCaseParamsError("chatbot_role is required")
                )
            else:
                instance.measure = AsyncMock(
                    return_value=MetricResult(score=0.9, threshold=threshold, passed=True, error=None)
                )
            return instance

        mock_metric_factory.create.side_effect = create
        orchestrator = EvaluationOrchestrator(config=stub_config)

        result = await orchestrator.evaluate(
            trace=trace, bot_id="test_conversation_bot", metric_names=["role_adherence", "bias"]
        )

        failed = result.metrics["role_adherence"]
        assert failed.score is None
        assert failed.passed is False
        assert failed.error is not None
        assert failed.error.category == "MissingTestCaseParamsError"
        assert result.metrics["bias"].passed is True


class TestMalformedOptInConfigIsolatedNotBlocking:
    async def test_malformed_opt_in_config_isolated_not_blocking(
        self, stub_config, mock_metric_factory, mock_llm_provider_factory, trace
    ):
        class _FakeNativeJsonCorrectness:
            def __init__(self, threshold: float = 0.5, model=None, async_mode=True):
                pass

        class _FakeJsonCorrectnessWrapper:
            _native_metric_cls = _FakeNativeJsonCorrectness

        class _FakeNativeBias:
            def __init__(self, threshold: float = 0.5, model=None, async_mode=True):
                pass

        class _FakeBiasWrapper:
            _native_metric_cls = _FakeNativeBias

        mock_metric_factory._registry = {
            "json_correctness": _FakeJsonCorrectnessWrapper,
            "bias": _FakeBiasWrapper,
        }

        def create(name, *, threshold, deepeval_model, **options):
            instance = MagicMock()
            instance.measure = AsyncMock(
                return_value=MetricResult(score=0.9, threshold=threshold, passed=True, error=None)
            )
            return instance

        mock_metric_factory.create.side_effect = create

        resolver = MagicMock()

        def resolve_options(bot_id, names):
            name = names[0]
            if name == "json_correctness":
                raise ImportError("no module named 'bad.module.path'")
            return {name: {}}

        resolver.resolve_options.side_effect = resolve_options

        orchestrator = EvaluationOrchestrator(config=stub_config, resolver=resolver)

        result = await orchestrator.evaluate(
            trace=trace, bot_id="test_rag_bot", metric_names=["json_correctness", "bias"]
        )

        failed = result.metrics["json_correctness"]
        assert failed.score is None
        assert failed.passed is False
        assert failed.error is not None
        assert result.metrics["bias"].passed is True


class TestMetricWrapperConstructionFailureIsolatedNotBlocking:
    async def test_metric_wrapper_construction_failure_isolated_not_blocking(
        self, stub_config, mock_metric_factory, mock_llm_provider_factory, trace
    ):
        class _FakeNativeBias:
            def __init__(self, threshold: float = 0.5, model=None, async_mode=True):
                pass

        class _FakeBiasWrapper:
            _native_metric_cls = _FakeNativeBias

        class _FakeJsonCorrectnessWrapperRaisesOnInit:
            _native_metric_cls = _FakeNativeBias

        mock_metric_factory._registry = {
            "json_correctness": _FakeJsonCorrectnessWrapperRaisesOnInit,
            "bias": _FakeBiasWrapper,
        }

        def create(name, *, threshold, deepeval_model, **options):
            if name == "json_correctness":
                raise TypeError("missing required keyword argument: 'expected_schema'")
            instance = MagicMock()
            instance.measure = AsyncMock(
                return_value=MetricResult(score=0.9, threshold=threshold, passed=True, error=None)
            )
            return instance

        mock_metric_factory.create.side_effect = create

        resolver = MagicMock()
        resolver.resolve_options.side_effect = lambda bot_id, names: {names[0]: {}}

        orchestrator = EvaluationOrchestrator(config=stub_config, resolver=resolver)

        result = await orchestrator.evaluate(
            trace=trace, bot_id="test_rag_bot", metric_names=["json_correctness", "bias"]
        )

        failed = result.metrics["json_correctness"]
        assert failed.score is None
        assert failed.passed is False
        assert failed.error is not None
        assert result.metrics["bias"].passed is True


class TestInvalidMessageRoleIsolatesOnlyConversationalMetrics:
    async def test_invalid_message_role_isolates_only_conversational_metrics(
        self, stub_config, mock_metric_factory, mock_llm_provider_factory
    ):
        trace = NormalizedTrace(
            input="hi",
            output="hello",
            messages=[Message(role="system", content="You are a bot")],
        )

        try:
            Turn(role="system", content="You are a bot")
            raise AssertionError("expected Turn(role='system', ...) to raise ValidationError")
        except ValidationError as exc:
            role_validation_error = exc

        class _FakeNativeConversationCompleteness:
            def __init__(self, threshold: float = 0.5, model=None, async_mode=True):
                pass

        class _FakeConversationCompletenessWrapper:
            _native_metric_cls = _FakeNativeConversationCompleteness

        class _FakeNativeBias:
            def __init__(self, threshold: float = 0.5, model=None, async_mode=True):
                pass

        class _FakeBiasWrapper:
            _native_metric_cls = _FakeNativeBias

        mock_metric_factory._registry = {
            "conversation_completeness": _FakeConversationCompletenessWrapper,
            "bias": _FakeBiasWrapper,
        }

        def create(name, *, threshold, deepeval_model, **options):
            instance = MagicMock()
            if name == "conversation_completeness":
                instance.measure = AsyncMock(side_effect=role_validation_error)
            else:
                instance.measure = AsyncMock(
                    return_value=MetricResult(score=0.9, threshold=threshold, passed=True, error=None)
                )
            return instance

        mock_metric_factory.create.side_effect = create
        orchestrator = EvaluationOrchestrator(config=stub_config)

        result = await orchestrator.evaluate(
            trace=trace,
            bot_id="test_conversation_bot",
            metric_names=["conversation_completeness", "bias"],
        )

        failed = result.metrics["conversation_completeness"]
        assert failed.score is None
        assert failed.passed is False
        assert failed.error is not None
        assert failed.error.category == "ValidationError"
        assert result.metrics["bias"].passed is True


class TestEmptyOrSingleTurnMessagesIsolatesOnlyMultiTurnConversationalMetrics:
    @pytest.mark.parametrize(
        "messages",
        [
            [],
            [Message(role="user", content="Hi")],
        ],
    )
    async def test_empty_or_single_turn_messages_isolates_only_multi_turn_conversational_metrics(
        self, stub_config, mock_metric_factory, mock_llm_provider_factory, messages
    ):
        trace = NormalizedTrace(input="hi", output="hello", messages=messages)

        missing_params_error = MissingTestCaseParamsError(
            "ConversationalTestCase requires at least one Turn"
        )

        multi_turn_names = [
            "conversation_completeness",
            "turn_relevancy",
            "knowledge_retention",
            "role_adherence",
            "conversational_g_eval",
        ]

        class _FakeNativeBias:
            def __init__(self, threshold: float = 0.5, model=None, async_mode=True):
                pass

        class _FakeBiasWrapper:
            _native_metric_cls = _FakeNativeBias

        fake_registry = {"bias": _FakeBiasWrapper}
        for name in multi_turn_names:
            fake_native = type(
                f"_FakeNative_{name}",
                (),
                {"__init__": lambda self, threshold=0.5, model=None, async_mode=True: None},
            )
            fake_registry[name] = type(
                f"_Fake_{name}_Wrapper", (), {"_native_metric_cls": fake_native}
            )

        mock_metric_factory._registry = fake_registry

        def create(name, *, threshold, deepeval_model, **options):
            instance = MagicMock()
            if name in multi_turn_names:
                instance.measure = AsyncMock(side_effect=missing_params_error)
            else:
                instance.measure = AsyncMock(
                    return_value=MetricResult(score=0.9, threshold=threshold, passed=True, error=None)
                )
            return instance

        mock_metric_factory.create.side_effect = create
        orchestrator = EvaluationOrchestrator(config=stub_config)

        result = await orchestrator.evaluate(
            trace=trace,
            bot_id="test_conversation_bot",
            metric_names=[*multi_turn_names, "bias"],
        )

        for name in multi_turn_names:
            failed = result.metrics[name]
            assert failed.score is None
            assert failed.passed is False
            assert failed.error is not None
            assert failed.error.category == "MissingTestCaseParamsError"
        assert result.metrics["bias"].passed is True


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

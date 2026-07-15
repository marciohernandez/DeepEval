"""Unit tests for RagasMetricWrapper self-registration (M3.4, US3, FR-008/FR-009/FR-010/FR-014).

`RagasMetricWrapper` overrides `measure()` directly (no native DeepEval BaseMetric to delegate
to, research.md §R3/§R4). Two thin subclasses back the `ragas_answer_correctness` and
`ragas_context_recall` canonical names; the `ragas.*` imports inside `ragas_metric.py` are
guarded so a missing `ragas` install isolates to whichever Ragas metric a bot opts into
(research.md §R5).
"""
from __future__ import annotations

import inspect
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from deepeval.models.base_model import DeepEvalBaseLLM

from deepeval_platform.evaluation.evaluation_context import EvaluationContext
from deepeval_platform.evaluation.evaluation_result import MetricResult
from deepeval_platform.evaluation.metrics.metric_base import MetricBase
from deepeval_platform.evaluation.metrics.metric_factory import MetricFactory
from deepeval_platform.evaluation.metrics.native import ragas_metric
from deepeval_platform.normalization.models import NormalizedTrace


def _stub_config() -> MagicMock:
    config = MagicMock()
    config.get.side_effect = lambda key: {
        "embedding.model": "text-embedding-3-small",
        "embedding.dimensions": "1536",
        "OPENAI_API_KEY": "test-openai-key",
    }[key]
    return config


class TestRagasMetricWrapperRegistration:
    def test_answer_correctness_registered_under_canonical_name(self):
        assert issubclass(
            MetricFactory._registry["ragas_answer_correctness"], ragas_metric.RagasMetricWrapper
        )

    def test_context_recall_registered_under_canonical_name(self):
        assert issubclass(
            MetricFactory._registry["ragas_context_recall"], ragas_metric.RagasMetricWrapper
        )

    def test_is_metric_base_subclass(self):
        assert issubclass(ragas_metric.RagasMetricWrapper, MetricBase)

    def test_answer_correctness_and_context_recall_are_distinct_classes(self):
        assert (
            MetricFactory._registry["ragas_answer_correctness"]
            is not MetricFactory._registry["ragas_context_recall"]
        )


class TestRagasMetricWrapperConstruction:
    def test_answer_correctness_constructs_llm_and_embeddings(self):
        stub_config = _stub_config()
        with (
            patch.object(ragas_metric, "AnswerCorrectness") as mock_answer_correctness,
            patch.object(ragas_metric, "RagasLLMAdapter") as mock_adapter_cls,
            patch.object(ragas_metric, "OpenAIEmbeddings") as mock_embeddings_cls,
            patch.object(ragas_metric, "LangchainEmbeddingsWrapper") as mock_wrapper_cls,
            patch.object(ragas_metric.ConfigManager, "instance", return_value=stub_config),
        ):
            wrapper_cls = MetricFactory._registry["ragas_answer_correctness"]
            wrapper_cls(threshold=0.5, deepeval_model=MagicMock(spec=DeepEvalBaseLLM))

        mock_embeddings_cls.assert_called_once_with(
            model="text-embedding-3-small", api_key="test-openai-key"
        )
        mock_wrapper_cls.assert_called_once_with(mock_embeddings_cls.return_value)
        mock_answer_correctness.assert_called_once_with(
            llm=mock_adapter_cls.return_value, embeddings=mock_wrapper_cls.return_value
        )

    def test_context_recall_constructs_llm_only(self):
        stub_config = _stub_config()
        with (
            patch.object(ragas_metric, "ContextRecall") as mock_context_recall,
            patch.object(ragas_metric, "RagasLLMAdapter") as mock_adapter_cls,
            patch.object(ragas_metric, "OpenAIEmbeddings") as mock_embeddings_cls,
            patch.object(ragas_metric, "LangchainEmbeddingsWrapper") as mock_wrapper_cls,
            patch.object(ragas_metric.ConfigManager, "instance", return_value=stub_config),
        ):
            wrapper_cls = MetricFactory._registry["ragas_context_recall"]
            wrapper_cls(threshold=0.5, deepeval_model=MagicMock(spec=DeepEvalBaseLLM))

        mock_context_recall.assert_called_once_with(llm=mock_adapter_cls.return_value)
        mock_embeddings_cls.assert_not_called()
        mock_wrapper_cls.assert_not_called()
        stub_config.get.assert_not_called()


class TestRagasMetricWrapperMeasure:
    async def test_measure_builds_single_turn_sample_and_maps_score_for_answer_correctness(self):
        trace = NormalizedTrace(
            input="What is the refund policy?",
            output="Refunds are processed within 5 business days.",
            expected_output="Refunds within 5 business days.",
            context=["Refund policy document excerpt."],
        )
        context = EvaluationContext(trace=trace, thresholds={})

        with (
            patch.object(ragas_metric, "AnswerCorrectness"),
            patch.object(ragas_metric, "RagasLLMAdapter"),
            patch.object(ragas_metric, "OpenAIEmbeddings"),
            patch.object(ragas_metric, "LangchainEmbeddingsWrapper"),
            patch.object(ragas_metric.ConfigManager, "instance", return_value=_stub_config()),
        ):
            wrapper_cls = MetricFactory._registry["ragas_answer_correctness"]
            metric = wrapper_cls(threshold=0.5, deepeval_model=MagicMock(spec=DeepEvalBaseLLM))
        metric._ragas_metric.single_turn_ascore = AsyncMock(return_value=0.83)

        result = await metric.measure(context)

        sample = metric._ragas_metric.single_turn_ascore.call_args[0][0]
        assert sample.user_input == "What is the refund policy?"
        assert sample.response == "Refunds are processed within 5 business days."
        assert sample.reference == "Refunds within 5 business days."
        assert result == MetricResult(score=0.83, threshold=0.5, passed=True, error=None)

    async def test_measure_builds_single_turn_sample_and_maps_score_for_context_recall(self):
        trace = NormalizedTrace(
            input="What is the refund policy?",
            output="Refunds are processed within 5 business days.",
            expected_output="Refunds within 5 business days.",
            context=["Refund policy document excerpt."],
        )
        context = EvaluationContext(trace=trace, thresholds={})

        with patch.object(ragas_metric, "ContextRecall"), patch.object(
            ragas_metric, "RagasLLMAdapter"
        ):
            wrapper_cls = MetricFactory._registry["ragas_context_recall"]
            metric = wrapper_cls(threshold=0.9, deepeval_model=MagicMock(spec=DeepEvalBaseLLM))
        metric._ragas_metric.single_turn_ascore = AsyncMock(return_value=0.83)

        result = await metric.measure(context)

        sample = metric._ragas_metric.single_turn_ascore.call_args[0][0]
        assert sample.user_input == "What is the refund policy?"
        assert sample.reference == "Refunds within 5 business days."
        assert sample.retrieved_contexts == ["Refund policy document excerpt."]
        assert result == MetricResult(score=0.83, threshold=0.9, passed=False, error=None)

    async def test_threshold_and_passed_properties_reflect_plain_attributes(self):
        with patch.object(ragas_metric, "ContextRecall"), patch.object(
            ragas_metric, "RagasLLMAdapter"
        ):
            wrapper_cls = MetricFactory._registry["ragas_context_recall"]
            metric = wrapper_cls(threshold=0.7, deepeval_model=MagicMock(spec=DeepEvalBaseLLM))

        assert metric.threshold == 0.7
        assert metric.passed is None

        metric._ragas_metric.single_turn_ascore = AsyncMock(return_value=0.9)
        await metric.measure(EvaluationContext(trace=NormalizedTrace(), thresholds={}))
        assert metric.passed is True


class TestRagasMetricWrapperOrchestratorFallback:
    def test_native_metric_cls_exposes_threshold_default_of_0_5_for_orchestrator_fallback(self):
        native_cls = MetricFactory._registry["ragas_answer_correctness"]._native_metric_cls
        assert (
            inspect.signature(native_cls.__init__).parameters["threshold"].default == 0.5
        )


class TestRagasMetricWrapperMissingDependency:
    def test_constructor_raises_import_error_when_ragas_unavailable_without_breaking_registration(
        self,
    ):
        original = ragas_metric._RAGAS_IMPORT_ERROR
        ragas_metric._RAGAS_IMPORT_ERROR = ImportError("ragas is not installed")
        try:
            assert "ragas_answer_correctness" in MetricFactory._registry
            assert "ragas_context_recall" in MetricFactory._registry

            ac_cls = MetricFactory._registry["ragas_answer_correctness"]
            cr_cls = MetricFactory._registry["ragas_context_recall"]

            with pytest.raises(ImportError):
                ac_cls(threshold=0.5, deepeval_model=MagicMock(spec=DeepEvalBaseLLM))

            with pytest.raises(ImportError):
                cr_cls(threshold=0.5, deepeval_model=MagicMock(spec=DeepEvalBaseLLM))
        finally:
            ragas_metric._RAGAS_IMPORT_ERROR = original

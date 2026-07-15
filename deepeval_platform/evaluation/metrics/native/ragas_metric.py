"""RagasMetricWrapper — backs 'ragas_answer_correctness' and 'ragas_context_recall' (M3.4, US3,
FR-008/FR-009/FR-010/FR-014).

The one deliberate MetricBase exception (research.md §R4): no native DeepEval class to delegate
to, so `measure()` is overridden directly against Ragas' own `single_turn_ascore` entry point
instead of `a_measure()`. The `ragas.*` imports below are guarded so a missing `ragas` install
never breaks module import — every other metric's registration keeps working, and the failure
is isolated to whichever Ragas metric a bot actually opts into (research.md §R5).
"""
from __future__ import annotations

from typing import ClassVar, Literal

from deepeval.models.base_model import DeepEvalBaseLLM
from langchain_openai import OpenAIEmbeddings

from deepeval_platform.config.config_manager import ConfigManager
from deepeval_platform.evaluation.evaluation_context import EvaluationContext
from deepeval_platform.evaluation.evaluation_result import MetricResult
from deepeval_platform.evaluation.metrics.metric_base import MetricBase
from deepeval_platform.evaluation.metrics.metric_factory import MetricFactory

try:
    from ragas.dataset_schema import SingleTurnSample
    from ragas.embeddings import LangchainEmbeddingsWrapper
    from ragas.metrics import AnswerCorrectness, ContextRecall

    from deepeval_platform.llm.ragas_adapter import RagasLLMAdapter

    _RAGAS_IMPORT_ERROR: Exception | None = None
except ImportError as exc:  # pragma: no cover - exercised via monkeypatched flag in tests
    _RAGAS_IMPORT_ERROR = exc


class _RagasThresholdDefault:
    """Placeholder so `_native_default_threshold`'s unmodified `inspect.signature(...)` lookup
    keeps resolving a numeric default for a wrapper with no real native DeepEval class."""

    def __init__(self, threshold: float = 0.5) -> None: ...


class RagasMetricWrapper(MetricBase):
    _native_metric_cls: ClassVar[type] = _RagasThresholdDefault

    def __init__(
        self,
        threshold: float,
        deepeval_model: DeepEvalBaseLLM,
        ragas_metric_name: Literal["answer_correctness", "context_recall"],
        config: ConfigManager | None = None,
    ) -> None:
        if _RAGAS_IMPORT_ERROR is not None:
            raise ImportError(
                "ragas is not installed; run `uv sync`"
            ) from _RAGAS_IMPORT_ERROR

        self._threshold = threshold
        self._ragas_metric_name = ragas_metric_name
        self._passed: bool | None = None

        judge = RagasLLMAdapter(deepeval_model)

        if ragas_metric_name == "answer_correctness":
            resolved_config = config if config is not None else ConfigManager.instance()
            embedding_model = resolved_config.get("embedding.model")
            resolved_config.get("embedding.dimensions")
            openai_api_key = resolved_config.get("OPENAI_API_KEY")
            embeddings = OpenAIEmbeddings(model=embedding_model, api_key=openai_api_key)
            wrapped_embeddings = LangchainEmbeddingsWrapper(embeddings)
            self._ragas_metric = AnswerCorrectness(llm=judge, embeddings=wrapped_embeddings)
        else:
            self._ragas_metric = ContextRecall(llm=judge)

    @property
    def threshold(self) -> float:
        return self._threshold

    @property
    def passed(self) -> bool | None:
        return self._passed

    async def measure(self, context: EvaluationContext) -> MetricResult:
        trace = context.trace
        sample_kwargs: dict[str, object] = {
            "user_input": trace.input,
            "reference": trace.expected_output,
        }
        if self._ragas_metric_name == "answer_correctness":
            sample_kwargs["response"] = trace.output
        else:
            sample_kwargs["retrieved_contexts"] = list(trace.context)

        sample = SingleTurnSample(**sample_kwargs)
        score = await self._ragas_metric.single_turn_ascore(sample)
        self._passed = score >= self._threshold
        return MetricResult(score=score, threshold=self._threshold, passed=self._passed, error=None)


@MetricFactory.register("ragas_answer_correctness")
class _AnswerCorrectnessMetricWrapper(RagasMetricWrapper):
    def __init__(self, threshold: float, deepeval_model: DeepEvalBaseLLM) -> None:
        super().__init__(
            threshold=threshold,
            deepeval_model=deepeval_model,
            ragas_metric_name="answer_correctness",
        )


@MetricFactory.register("ragas_context_recall")
class _ContextRecallMetricWrapper(RagasMetricWrapper):
    def __init__(self, threshold: float, deepeval_model: DeepEvalBaseLLM) -> None:
        super().__init__(
            threshold=threshold,
            deepeval_model=deepeval_model,
            ragas_metric_name="context_recall",
        )

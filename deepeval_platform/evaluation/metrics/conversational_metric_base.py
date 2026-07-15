"""ConversationalMetricBase — ABC adapting one native DeepEval BaseConversationalMetric (M3.3).

Sibling to MetricBase (research.md §R8), not a subclass — the two test-case types share no
common constructor shape worth abstracting over. Delegates all scoring to the wrapped native
metric (Principle II — DeepEval-First); this class only maps NormalizedTrace.messages ->
ConversationalTestCase (data-model.md) and native metric state -> MetricResult.
"""
from __future__ import annotations

from abc import ABC
from typing import ClassVar

from deepeval.metrics.base_metric import BaseConversationalMetric
from deepeval.models.base_model import DeepEvalBaseLLM
from deepeval.test_case import ConversationalTestCase, Turn

from deepeval_platform.evaluation.evaluation_context import EvaluationContext
from deepeval_platform.evaluation.evaluation_result import MetricResult
from deepeval_platform.normalization.models import NormalizedTrace


class ConversationalMetricBase(ABC):
    _native_metric_cls: ClassVar[type[BaseConversationalMetric]]

    def __init__(self, threshold: float, deepeval_model: DeepEvalBaseLLM) -> None:
        self._native = self._native_metric_cls(
            threshold=threshold, model=deepeval_model, async_mode=True
        )

    @property
    def threshold(self) -> float:
        return self._native.threshold

    @property
    def passed(self) -> bool | None:
        return self._native.success

    async def measure(self, context: EvaluationContext) -> MetricResult:
        test_case = self._build_test_case(context.trace)
        await self._native.a_measure(test_case, _show_indicator=False)
        return MetricResult(
            score=self._native.score,
            threshold=self._native.threshold,
            passed=self._native.success,
            error=None,
        )

    @staticmethod
    def _build_test_case(
        trace: NormalizedTrace, chatbot_role: str | None = None
    ) -> ConversationalTestCase:
        return ConversationalTestCase(
            turns=[Turn(role=m.role, content=m.content) for m in trace.messages],
            chatbot_role=chatbot_role,
        )

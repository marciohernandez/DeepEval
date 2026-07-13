"""MetricBase — ABC adapting one native DeepEval BaseMetric to this project's contract (M3.1).

Delegates all scoring to the wrapped native metric (Principle II — DeepEval-First); this class
only maps NormalizedTrace -> LLMTestCase (research.md §7) and native metric state -> MetricResult.
"""
from __future__ import annotations

from abc import ABC
from typing import ClassVar

from deepeval.metrics.base_metric import BaseMetric
from deepeval.models.base_model import DeepEvalBaseLLM
from deepeval.test_case import LLMTestCase, ToolCall

from deepeval_platform.evaluation.evaluation_context import EvaluationContext
from deepeval_platform.evaluation.evaluation_result import MetricResult
from deepeval_platform.normalization.models import NormalizedTrace


class MetricBase(ABC):
    _native_metric_cls: ClassVar[type[BaseMetric]]

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
    def _build_test_case(trace: NormalizedTrace) -> LLMTestCase:
        return LLMTestCase(
            input=trace.input,
            actual_output=trace.output,
            expected_output=trace.expected_output,
            retrieval_context=trace.context,
            tools_called=[
                ToolCall(
                    name=tool_call.name,
                    input_parameters=tool_call.input_parameters,
                    output=tool_call.output,
                )
                for tool_call in trace.tools_called
            ],
        )

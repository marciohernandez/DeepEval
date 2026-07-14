"""HallucinationMetricWrapper — self-registers under 'hallucination' (M3.2, US2).

Overrides _build_test_case (scoped to this subclass only, FR-007) to populate
LLMTestCase.context, which HallucinationMetric requires but MetricBase does not set.
"""
from __future__ import annotations

from deepeval.metrics import HallucinationMetric
from deepeval.test_case import LLMTestCase, ToolCall

from deepeval_platform.evaluation.metrics.metric_base import MetricBase
from deepeval_platform.evaluation.metrics.metric_factory import MetricFactory
from deepeval_platform.normalization.models import NormalizedTrace


@MetricFactory.register("hallucination")
class HallucinationMetricWrapper(MetricBase):
    _native_metric_cls = HallucinationMetric

    @staticmethod
    def _build_test_case(trace: NormalizedTrace) -> LLMTestCase:
        return LLMTestCase(
            input=trace.input,
            actual_output=trace.output,
            expected_output=trace.expected_output,
            context=trace.context,
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

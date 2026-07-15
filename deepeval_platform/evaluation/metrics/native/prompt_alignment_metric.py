"""PromptAlignmentMetricWrapper — self-registers under 'prompt_alignment' (M3.3, US4, FR-010).

`prompt_instructions` is bot-configured (BotMetricConfigResolver reconstructs the list from
indexed bots.yaml keys) and forwarded straight to the native constructor.
"""
from __future__ import annotations

from deepeval.metrics import PromptAlignmentMetric
from deepeval.models.base_model import DeepEvalBaseLLM

from deepeval_platform.evaluation.metrics.metric_base import MetricBase
from deepeval_platform.evaluation.metrics.metric_factory import MetricFactory


@MetricFactory.register("prompt_alignment")
class PromptAlignmentMetricWrapper(MetricBase):
    _native_metric_cls = PromptAlignmentMetric

    def __init__(
        self, threshold: float, deepeval_model: DeepEvalBaseLLM, prompt_instructions: list[str]
    ) -> None:
        self._native = PromptAlignmentMetric(
            threshold=threshold,
            model=deepeval_model,
            prompt_instructions=prompt_instructions,
            async_mode=True,
        )

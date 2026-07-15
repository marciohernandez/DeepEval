"""ConversationalGEvalMetricWrapper — self-registers under 'conversational_g_eval' (M3.3, US4, FR-010).

`criteria` is bot-configured (`bots.<bot>.conversational_geval_criteria`); `name` is a fixed
literal — not bot-configurable this milestone (data-model.md).
"""
from __future__ import annotations

from deepeval.metrics import ConversationalGEval
from deepeval.models.base_model import DeepEvalBaseLLM

from deepeval_platform.evaluation.metrics.conversational_metric_base import (
    ConversationalMetricBase,
)
from deepeval_platform.evaluation.metrics.metric_factory import MetricFactory


@MetricFactory.register("conversational_g_eval")
class ConversationalGEvalMetricWrapper(ConversationalMetricBase):
    _native_metric_cls = ConversationalGEval

    def __init__(self, threshold: float, deepeval_model: DeepEvalBaseLLM, criteria: str) -> None:
        self._native = ConversationalGEval(
            name="Conversational Quality",
            criteria=criteria,
            threshold=threshold,
            model=deepeval_model,
            async_mode=True,
        )

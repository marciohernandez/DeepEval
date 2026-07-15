"""GEvalMetricWrapper — self-registers under 'g_eval' (M3.4, US1, FR-001/FR-002).

`criteria` is bot-configured (`bots.<bot>.geval_criteria`); `name` is a fixed literal, matching
`ConversationalGEvalMetricWrapper`'s precedent (M3.3). `evaluation_params` is fixed at
construction — native `GEval.measure()`/`a_measure()` raise `ValueError` when it is falsy
(research.md §R1).
"""
from __future__ import annotations

from deepeval.metrics import GEval
from deepeval.models.base_model import DeepEvalBaseLLM
from deepeval.test_case import SingleTurnParams

from deepeval_platform.evaluation.metrics.metric_base import MetricBase
from deepeval_platform.evaluation.metrics.metric_factory import MetricFactory


@MetricFactory.register("g_eval")
class GEvalMetricWrapper(MetricBase):
    _native_metric_cls = GEval

    def __init__(self, threshold: float, deepeval_model: DeepEvalBaseLLM, criteria: str) -> None:
        self._native = GEval(
            name="Custom Criteria",
            criteria=criteria,
            evaluation_params=[SingleTurnParams.INPUT, SingleTurnParams.ACTUAL_OUTPUT],
            threshold=threshold,
            model=deepeval_model,
            async_mode=True,
        )

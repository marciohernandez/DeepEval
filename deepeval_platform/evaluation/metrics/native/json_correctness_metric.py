"""JsonCorrectnessMetricWrapper — self-registers under 'json_correctness' (M3.3, US4, FR-010).

`expected_schema` is bot-configured (BotMetricConfigResolver resolves the dotted `bots.yaml`
path into a live class) and forwarded straight to the native constructor.
"""
from __future__ import annotations

from deepeval.metrics import JsonCorrectnessMetric
from deepeval.models.base_model import DeepEvalBaseLLM
from pydantic import BaseModel

from deepeval_platform.evaluation.metrics.metric_base import MetricBase
from deepeval_platform.evaluation.metrics.metric_factory import MetricFactory


@MetricFactory.register("json_correctness")
class JsonCorrectnessMetricWrapper(MetricBase):
    _native_metric_cls = JsonCorrectnessMetric

    def __init__(
        self, threshold: float, deepeval_model: DeepEvalBaseLLM, expected_schema: type[BaseModel]
    ) -> None:
        self._native = JsonCorrectnessMetric(
            threshold=threshold,
            model=deepeval_model,
            expected_schema=expected_schema,
            async_mode=True,
        )

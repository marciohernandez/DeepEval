"""DAGMetricWrapper — self-registers under 'dag' (M3.4, US2, FR-004/FR-005).

`dag` is a live `DeepAcyclicGraph` instance, already resolved/invoked by `BotMetricConfigResolver`
by the time it reaches this wrapper (research.md §R2); `name` is a fixed literal.
"""
from __future__ import annotations

from deepeval.metrics import DAGMetric
from deepeval.metrics.dag import DeepAcyclicGraph
from deepeval.models.base_model import DeepEvalBaseLLM

from deepeval_platform.evaluation.metrics.metric_base import MetricBase
from deepeval_platform.evaluation.metrics.metric_factory import MetricFactory


@MetricFactory.register("dag")
class DAGMetricWrapper(MetricBase):
    _native_metric_cls = DAGMetric

    def __init__(
        self, threshold: float, deepeval_model: DeepEvalBaseLLM, dag: DeepAcyclicGraph
    ) -> None:
        self._native = DAGMetric(
            name="Decision Graph",
            dag=dag,
            threshold=threshold,
            model=deepeval_model,
            async_mode=True,
        )

"""Unit tests for DAGMetricWrapper self-registration (M3.4, US2, FR-004/FR-005).

`dag` is a live `DeepAcyclicGraph` instance, already constructed/invoked by the time it reaches
this wrapper (resolution/invocation happens in `BotMetricConfigResolver`, not here); `name` is a
fixed literal (data-model.md).
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from deepeval.metrics import DAGMetric
from deepeval.metrics.dag import DeepAcyclicGraph
from deepeval.models.base_model import DeepEvalBaseLLM

from deepeval_platform.evaluation.metrics.metric_base import MetricBase
from deepeval_platform.evaluation.metrics.metric_factory import MetricFactory
from deepeval_platform.evaluation.metrics.native.dag_metric import DAGMetricWrapper


class TestDAGMetricWrapper:
    def test_registered_under_canonical_name(self):
        assert MetricFactory._registry["dag"] is DAGMetricWrapper

    def test_wraps_native_dag_metric(self):
        assert DAGMetricWrapper._native_metric_cls is DAGMetric

    def test_is_metric_base_subclass(self):
        assert issubclass(DAGMetricWrapper, MetricBase)

    def test_dag_instance_forwarded_to_native_constructor(self):
        # Real DAGMetric.__init__ deep-copies its `dag` arg (copy_graph) and eagerly reads
        # dag.root_nodes/dag.multiturn, so a plain mock can't reach an `is`-identity assertion on
        # metric._native.dag — patch the native class to verify the wrapper forwards `dag`
        # unchanged to DAGMetric's constructor.
        dag = MagicMock(spec=DeepAcyclicGraph)
        with patch(
            "deepeval_platform.evaluation.metrics.native.dag_metric.DAGMetric"
        ) as mock_dag_metric:
            DAGMetricWrapper(
                threshold=0.5,
                deepeval_model=MagicMock(spec=DeepEvalBaseLLM),
                dag=dag,
            )
        _, kwargs = mock_dag_metric.call_args
        assert kwargs["dag"] is dag
        assert kwargs["name"]

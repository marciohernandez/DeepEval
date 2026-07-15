"""Unit tests for JsonCorrectnessMetricWrapper self-registration (M3.3, US4, FR-010)."""
from __future__ import annotations

from unittest.mock import MagicMock

from deepeval.metrics import JsonCorrectnessMetric
from deepeval.models.base_model import DeepEvalBaseLLM
from pydantic import BaseModel

from deepeval_platform.evaluation.metrics.metric_factory import MetricFactory
from deepeval_platform.evaluation.metrics.native.json_correctness_metric import (
    JsonCorrectnessMetricWrapper,
)


class _DummySchema(BaseModel):
    order_id: str


class TestJsonCorrectnessMetricWrapper:
    def test_registered_under_canonical_name(self):
        assert MetricFactory._registry["json_correctness"] is JsonCorrectnessMetricWrapper

    def test_wraps_native_json_correctness_metric(self):
        assert JsonCorrectnessMetricWrapper._native_metric_cls is JsonCorrectnessMetric

    def test_expected_schema_forwarded_to_native_constructor(self):
        metric = JsonCorrectnessMetricWrapper(
            threshold=0.5,
            deepeval_model=MagicMock(spec=DeepEvalBaseLLM),
            expected_schema=_DummySchema,
        )
        assert metric._native.expected_schema is _DummySchema

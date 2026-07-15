"""Unit tests for PromptAlignmentMetricWrapper self-registration (M3.3, US4, FR-010)."""
from __future__ import annotations

from unittest.mock import MagicMock

from deepeval.metrics import PromptAlignmentMetric
from deepeval.models.base_model import DeepEvalBaseLLM

from deepeval_platform.evaluation.metrics.metric_factory import MetricFactory
from deepeval_platform.evaluation.metrics.native.prompt_alignment_metric import (
    PromptAlignmentMetricWrapper,
)


class TestPromptAlignmentMetricWrapper:
    def test_registered_under_canonical_name(self):
        assert MetricFactory._registry["prompt_alignment"] is PromptAlignmentMetricWrapper

    def test_wraps_native_prompt_alignment_metric(self):
        assert PromptAlignmentMetricWrapper._native_metric_cls is PromptAlignmentMetric

    def test_prompt_instructions_forwarded_to_native_constructor(self):
        metric = PromptAlignmentMetricWrapper(
            threshold=0.5,
            deepeval_model=MagicMock(spec=DeepEvalBaseLLM),
            prompt_instructions=["Always respond in JSON"],
        )
        assert metric._native.prompt_instructions == ["Always respond in JSON"]

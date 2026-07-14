"""Unit test for HallucinationMetricWrapper self-registration and test-case override (M3.2, US2)."""
from __future__ import annotations

from deepeval.metrics import HallucinationMetric

from deepeval_platform.evaluation.metrics.metric_factory import MetricFactory
from deepeval_platform.evaluation.metrics.native.hallucination_metric import (
    HallucinationMetricWrapper,
)
from deepeval_platform.normalization.models import NormalizedTrace


class TestHallucinationMetricWrapper:
    def test_registered_under_canonical_name(self):
        assert MetricFactory._registry["hallucination"] is HallucinationMetricWrapper

    def test_wraps_native_hallucination_metric(self):
        assert HallucinationMetricWrapper._native_metric_cls is HallucinationMetric

    def test_build_test_case_populates_context_field(self):
        trace = NormalizedTrace(
            input="What is the refund policy?",
            output="Refunds within 30 days.",
            context=["ctx1", "ctx2"],
            expected_output="Refunds within 30 days.",
        )

        test_case = HallucinationMetricWrapper._build_test_case(trace)

        assert test_case.context == ["ctx1", "ctx2"]
        assert test_case.retrieval_context == ["ctx1", "ctx2"]
        assert test_case.input == trace.input
        assert test_case.actual_output == trace.output
        assert test_case.expected_output == trace.expected_output
        assert test_case.tools_called == []

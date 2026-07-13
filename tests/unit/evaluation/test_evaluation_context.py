"""Unit tests for EvaluationContext (M3.1, data-model.md, FR-003)."""
from __future__ import annotations

from deepeval_platform.evaluation.evaluation_context import EvaluationContext
from deepeval_platform.normalization.models import NormalizedTrace


class TestEvaluationContext:
    def test_is_two_field_dataclass(self):
        trace = NormalizedTrace(input="q", output="a")
        thresholds = {"faithfulness": 0.8}
        context = EvaluationContext(trace=trace, thresholds=thresholds)
        assert context.trace is trace
        assert context.thresholds is thresholds

    def test_round_trips_trace_and_thresholds_unmodified(self):
        trace = NormalizedTrace(
            input="What is the refund policy?",
            output="Refunds within 30 days.",
            context=["Our policy allows returns within 30 days."],
        )
        thresholds = {"answer_relevancy": 0.7, "faithfulness": 0.8}
        context = EvaluationContext(trace=trace, thresholds=thresholds)

        assert context.trace.input == "What is the refund policy?"
        assert context.trace.output == "Refunds within 30 days."
        assert context.trace.context == ["Our policy allows returns within 30 days."]
        assert context.thresholds == {"answer_relevancy": 0.7, "faithfulness": 0.8}

    def test_only_two_fields(self):
        import dataclasses

        field_names = {f.name for f in dataclasses.fields(EvaluationContext)}
        assert field_names == {"trace", "thresholds"}

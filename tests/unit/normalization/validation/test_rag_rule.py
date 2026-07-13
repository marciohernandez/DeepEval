"""Unit tests for RagValidationRule (M2.2, US3 — FR-006, FR-007)."""
from __future__ import annotations

from deepeval_platform.normalization.models import NormalizedTrace
from deepeval_platform.normalization.validation.rules.rag_rule import RagValidationRule


class TestRequiredFields:
    def test_required_fields_matches_rag_minimum(self):
        assert RagValidationRule().required_fields() == [
            "input",
            "output",
            "context",
            "expected_output",
        ]


class TestValidate:
    def test_complete_rag_trace_is_valid_with_no_missing_fields(self):
        trace = NormalizedTrace(
            input="Q", output="A", context=["c1"], expected_output="E"
        )

        result = RagValidationRule().validate(trace)

        assert result.is_valid is True
        assert result.missing_fields == []

    def test_missing_context_is_invalid_and_names_context(self):
        trace = NormalizedTrace(input="Q", output="A", context=[], expected_output="E")

        result = RagValidationRule().validate(trace)

        assert result.is_valid is False
        assert "context" in result.missing_fields

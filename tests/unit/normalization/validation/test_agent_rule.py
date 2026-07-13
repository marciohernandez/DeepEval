"""Unit tests for AgentValidationRule (M2.2, US3 — FR-006, FR-007)."""
from __future__ import annotations

from deepeval_platform.normalization.models import NormalizedTrace, ToolCall
from deepeval_platform.normalization.validation.rules.agent_rule import AgentValidationRule


class TestRequiredFields:
    def test_required_fields_matches_agent_minimum(self):
        assert AgentValidationRule().required_fields() == ["input", "output", "tools_called"]


class TestValidate:
    def test_complete_agent_trace_is_valid_with_no_missing_fields(self):
        trace = NormalizedTrace(
            input="Q", output="A", tools_called=[ToolCall(name="search")]
        )

        result = AgentValidationRule().validate(trace)

        assert result.is_valid is True
        assert result.missing_fields == []

    def test_missing_tools_called_is_invalid_and_names_tools_called(self):
        trace = NormalizedTrace(input="Q", output="A", tools_called=[])

        result = AgentValidationRule().validate(trace)

        assert result.is_valid is False
        assert "tools_called" in result.missing_fields

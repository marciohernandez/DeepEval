"""Unit tests for ValidationRule registry facade (M2.2, US3 — FR-006, FR-008)."""
from __future__ import annotations

import pytest

from deepeval_platform.evaluation.bot_type import BotType, InvalidBotTypeError
from deepeval_platform.normalization.models import Message, NormalizedTrace, ToolCall
from deepeval_platform.normalization.validation.rule_registry import ValidationRule


def _complete_trace_for_all_bot_types() -> NormalizedTrace:
    return NormalizedTrace(
        input="Q",
        output="A",
        context=["c1"],
        expected_output="E",
        tools_called=[ToolCall(name="search")],
        messages=[Message(role="user", content="hi")],
    )


class TestDispatch:
    def test_dispatches_to_rag_rule_for_bot_type_rag(self):
        trace = NormalizedTrace(input="Q", output="A", context=[], expected_output="E")

        result = ValidationRule.check(trace, BotType.RAG)

        assert result.is_valid is False
        assert "context" in result.missing_fields

    def test_dispatches_to_agent_rule_for_bot_type_agent(self):
        trace = NormalizedTrace(input="Q", output="A", tools_called=[])

        result = ValidationRule.check(trace, BotType.AGENT)

        assert result.is_valid is False
        assert "tools_called" in result.missing_fields

    def test_dispatches_to_conversation_rule_for_bot_type_conversation(self):
        trace = NormalizedTrace(messages=[])

        result = ValidationRule.check(trace, BotType.CONVERSATION)

        assert result.is_valid is False
        assert "messages" in result.missing_fields


class TestRawStringCoercion:
    def test_accepts_raw_string_bot_type(self):
        trace = _complete_trace_for_all_bot_types()

        result = ValidationRule.check(trace, "rag")

        assert result.is_valid is True


class TestInvalidBotType:
    def test_unrecognized_bot_type_raises_invalid_bot_type_error(self):
        trace = _complete_trace_for_all_bot_types()

        with pytest.raises(InvalidBotTypeError):
            ValidationRule.check(trace, "not_a_real_bot_type")


class TestCompleteTraceValidAgainstAnyBotType:
    @pytest.mark.parametrize("bot_type", [BotType.RAG, BotType.AGENT, BotType.CONVERSATION])
    def test_complete_trace_valid_against_each_bot_type(self, bot_type):
        trace = _complete_trace_for_all_bot_types()

        result = ValidationRule.check(trace, bot_type)

        assert result.is_valid is True
        assert result.missing_fields == []


class TestMismatchedBotTypeNoCrossCheck:
    def test_mismatched_bot_type_request_just_runs_that_rule(self):
        # A trace shaped for CONVERSATION (has messages) but missing the fields
        # AGENT requires — requesting AGENT's rule is a caller error, not a
        # validation-layer concern; ValidationRule performs no cross-check.
        trace = NormalizedTrace(messages=[Message(role="user", content="hi")])

        result = ValidationRule.check(trace, BotType.AGENT)

        assert result.is_valid is False
        assert set(result.missing_fields) == {"input", "output", "tools_called"}

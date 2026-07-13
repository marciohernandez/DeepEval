"""Unit tests for ConversationValidationRule (M2.2, US3 — FR-006, FR-007)."""
from __future__ import annotations

from deepeval_platform.normalization.models import Message, NormalizedTrace
from deepeval_platform.normalization.validation.rules.conversation_rule import (
    ConversationValidationRule,
)


class TestRequiredFields:
    def test_required_fields_matches_conversation_minimum(self):
        assert ConversationValidationRule().required_fields() == ["messages"]


class TestValidate:
    def test_complete_conversation_trace_is_valid_with_no_missing_fields(self):
        trace = NormalizedTrace(messages=[Message(role="user", content="hi")])

        result = ConversationValidationRule().validate(trace)

        assert result.is_valid is True
        assert result.missing_fields == []

    def test_missing_messages_is_invalid_and_names_messages(self):
        trace = NormalizedTrace(messages=[])

        result = ConversationValidationRule().validate(trace)

        assert result.is_valid is False
        assert "messages" in result.missing_fields

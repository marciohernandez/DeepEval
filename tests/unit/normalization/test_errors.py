"""Unit tests for normalization-layer exceptions (M2.2, ConfigError/InvalidBotTypeError convention)."""
from __future__ import annotations

from deepeval_platform.normalization.errors import FieldMappingTypeError, UnmappedBotError


class TestUnmappedBotError:
    def test_message_contains_bot_id(self):
        error = UnmappedBotError("no_such_bot")
        assert "no_such_bot" in str(error)

    def test_carries_bot_id_attribute(self):
        error = UnmappedBotError("no_such_bot")
        assert error.bot_id == "no_such_bot"


class TestFieldMappingTypeError:
    def test_message_contains_all_diagnostic_fields(self):
        error = FieldMappingTypeError(
            bot_id="test_rag_bot",
            field="context",
            path="output.data.retrieved_contexts",
            resolved_type=str,
        )
        message = str(error)
        assert "test_rag_bot" in message
        assert "context" in message
        assert "output.data.retrieved_contexts" in message
        assert "str" in message

    def test_carries_diagnostic_attributes(self):
        error = FieldMappingTypeError(
            bot_id="test_rag_bot",
            field="context",
            path="output.data.retrieved_contexts",
            resolved_type=str,
        )
        assert error.bot_id == "test_rag_bot"
        assert error.field == "context"
        assert error.path == "output.data.retrieved_contexts"
        assert error.resolved_type is str

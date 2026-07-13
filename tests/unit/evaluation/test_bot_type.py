"""Unit tests for BotType and InvalidBotTypeError (US2 — Metric Selection)."""
from __future__ import annotations

import pytest

from deepeval_platform.evaluation.bot_type import BotType, InvalidBotTypeError


class TestBotTypeValidCoercion:
    def test_rag_coerces(self):
        assert BotType("rag") == BotType.RAG

    def test_agent_coerces(self):
        assert BotType("agent") == BotType.AGENT

    def test_conversation_coerces(self):
        assert BotType("conversation") == BotType.CONVERSATION

    def test_values_are_lowercase(self):
        assert BotType.RAG.value == "rag"
        assert BotType.AGENT.value == "agent"
        assert BotType.CONVERSATION.value == "conversation"


class TestBotTypeInvalidInput:
    def test_unknown_string_raises_value_error(self):
        with pytest.raises(ValueError):
            BotType("unknown")

    def test_none_raises_value_error(self):
        with pytest.raises(ValueError):
            BotType(None)

    def test_empty_string_raises_value_error(self):
        with pytest.raises(ValueError):
            BotType("")


class TestInvalidBotTypeError:
    def test_is_value_error_subclass(self):
        assert issubclass(InvalidBotTypeError, ValueError)

    def test_message_contains_received_value(self):
        err = InvalidBotTypeError("unknown_type")
        assert "unknown_type" in str(err)

    def test_message_contains_supported_values(self):
        err = InvalidBotTypeError("unknown_type")
        assert "rag" in str(err)
        assert "agent" in str(err)
        assert "conversation" in str(err)

    def test_stores_received_and_supported_attributes(self):
        err = InvalidBotTypeError("bogus")
        assert err.received == "bogus"
        assert set(err.supported) == {"rag", "agent", "conversation"}

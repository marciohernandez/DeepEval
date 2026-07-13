"""Unit tests for StrategyFactory (US2 — Metric Selection, FR-009, FR-010)."""
from __future__ import annotations

import pytest

from deepeval_platform.evaluation.bot_type import BotType, InvalidBotTypeError
from deepeval_platform.evaluation.strategies.agent_strategy import AgentStrategy
from deepeval_platform.evaluation.strategies.conversation_strategy import ConversationStrategy
from deepeval_platform.evaluation.strategies.rag_strategy import RAGStrategy
from deepeval_platform.evaluation.strategy_factory import StrategyFactory


class TestStrategyFactoryValidBotTypes:
    def test_rag_bot_type_returns_rag_strategy(self):
        assert isinstance(StrategyFactory.create(BotType.RAG), RAGStrategy)

    def test_agent_bot_type_returns_agent_strategy(self):
        assert isinstance(StrategyFactory.create(BotType.AGENT), AgentStrategy)

    def test_conversation_bot_type_returns_conversation_strategy(self):
        assert isinstance(StrategyFactory.create(BotType.CONVERSATION), ConversationStrategy)

    def test_raw_string_coercion_works(self):
        assert isinstance(StrategyFactory.create("rag"), RAGStrategy)
        assert isinstance(StrategyFactory.create("agent"), AgentStrategy)
        assert isinstance(StrategyFactory.create("conversation"), ConversationStrategy)

    def test_repeated_create_returns_same_concrete_type(self):
        """SC-004: create() is deterministic across repeated calls."""
        first = StrategyFactory.create(BotType.RAG)
        second = StrategyFactory.create(BotType.RAG)
        assert type(first) is type(second)


class TestStrategyFactoryInvalidBotTypes:
    def test_unknown_string_raises_invalid_bot_type_error(self):
        with pytest.raises(InvalidBotTypeError) as exc_info:
            StrategyFactory.create("unknown_type")
        assert "unknown_type" in str(exc_info.value)
        assert "rag" in str(exc_info.value)

    def test_none_raises_invalid_bot_type_error(self):
        with pytest.raises(InvalidBotTypeError):
            StrategyFactory.create(None)

    def test_empty_string_raises_invalid_bot_type_error(self):
        with pytest.raises(InvalidBotTypeError):
            StrategyFactory.create("")

    def test_error_message_lists_supported_values(self):
        with pytest.raises(InvalidBotTypeError) as exc_info:
            StrategyFactory.create("bogus")
        message = str(exc_info.value)
        assert "rag" in message
        assert "agent" in message
        assert "conversation" in message

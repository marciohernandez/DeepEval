"""Unit tests for BotInvokerFactory (M4.1, T019): dotted-class import/validation,
no fixed registry, no factory edit needed for a new invoker type.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from deepeval.test_case import Turn

from deepeval_platform.synthetic.bot_invoker_base import BotInvokerBase
from deepeval_platform.synthetic.bot_invoker_factory import (
    BotInvokerConfigError,
    BotInvokerFactory,
)
from deepeval_platform.synthetic.flowise_bot_invoker import FlowiseBotInvoker
from deepeval_platform.synthetic.langchain_bot_invoker import LangChainBotInvoker


class _CustomTestInvoker(BotInvokerBase):
    def __init__(self, bot_id: str, greeting: str) -> None:
        self.bot_id = bot_id
        self.greeting = greeting

    def __call__(self, input: str, turns: list[Turn], thread_id: str) -> Turn:
        return Turn(role="assistant", content=self.greeting)


class _NotAnInvoker:
    def __init__(self, bot_id: str) -> None:
        self.bot_id = bot_id


def _config(values: dict) -> MagicMock:
    config = MagicMock()
    config.get.side_effect = lambda key: values[key]
    return config


class TestConfiguredDottedSubclassesLoad:
    def test_flowise_invoker_loads_from_config(self):
        config = _config(
            {
                "bots.test_rag_bot.invocation.invoker_class": (
                    "deepeval_platform.synthetic.flowise_bot_invoker.FlowiseBotInvoker"
                ),
                "bots.test_rag_bot.invocation.endpoint_url": "https://flowise/api",
            }
        )

        invoker = BotInvokerFactory.create("test_rag_bot", config=config)

        assert isinstance(invoker, FlowiseBotInvoker)

    def test_langchain_invoker_loads_from_config(self):
        config = _config(
            {
                "bots.test_agent_bot.invocation.invoker_class": (
                    "deepeval_platform.synthetic.langchain_bot_invoker.LangChainBotInvoker"
                ),
                "bots.test_agent_bot.invocation.chain_target": "my_bots.agent_bot.graph",
            }
        )

        invoker = BotInvokerFactory.create("test_agent_bot", config=config)

        assert isinstance(invoker, LangChainBotInvoker)


class TestCustomSubclassNoRegistryEdit:
    def test_custom_test_subclass_loads_solely_from_config(self):
        config = _config(
            {
                "bots.custom_bot.invocation.invoker_class": (
                    "tests.unit.synthetic.test_bot_invoker_factory._CustomTestInvoker"
                ),
                "bots.custom_bot.invocation.greeting": "hello from custom invoker",
            }
        )

        invoker = BotInvokerFactory.create("custom_bot", config=config)

        assert isinstance(invoker, _CustomTestInvoker)
        turn = invoker(input="hi", turns=[], thread_id="t1")
        assert turn.content == "hello from custom invoker"


class TestFailureModes:
    def test_non_subclass_target_fails_clearly(self):
        config = _config(
            {
                "bots.bad_bot.invocation.invoker_class": (
                    "tests.unit.synthetic.test_bot_invoker_factory._NotAnInvoker"
                ),
            }
        )

        with pytest.raises(BotInvokerConfigError):
            BotInvokerFactory.create("bad_bot", config=config)

    def test_missing_target_fails_clearly(self):
        config = _config(
            {
                "bots.missing_bot.invocation.invoker_class": (
                    "deepeval_platform.synthetic.flowise_bot_invoker.DoesNotExist"
                ),
            }
        )

        with pytest.raises(BotInvokerConfigError):
            BotInvokerFactory.create("missing_bot", config=config)

    def test_abstract_target_fails_clearly(self):
        config = _config(
            {
                "bots.abstract_bot.invocation.invoker_class": (
                    "deepeval_platform.synthetic.bot_invoker_base.BotInvokerBase"
                ),
            }
        )

        with pytest.raises(BotInvokerConfigError):
            BotInvokerFactory.create("abstract_bot", config=config)

    def test_missing_config_key_fails_clearly(self):
        config = MagicMock()
        config.get.side_effect = KeyError("bots.no_config.invocation.invoker_class")

        with pytest.raises(BotInvokerConfigError):
            BotInvokerFactory.create("no_config", config=config)

    def test_missing_required_invoker_kwarg_fails_clearly(self):
        config = _config(
            {
                "bots.incomplete_bot.invocation.invoker_class": (
                    "deepeval_platform.synthetic.flowise_bot_invoker.FlowiseBotInvoker"
                ),
                # endpoint_url intentionally absent
            }
        )

        with pytest.raises(BotInvokerConfigError):
            BotInvokerFactory.create("incomplete_bot", config=config)

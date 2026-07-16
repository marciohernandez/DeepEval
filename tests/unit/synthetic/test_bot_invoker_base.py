"""Unit tests for BotInvokerBase ABC contract (M4.1, T016)."""
from __future__ import annotations

import inspect

import pytest
from deepeval.test_case import Turn

from deepeval_platform.synthetic.bot_invoker_base import BotInvokerBase


class TestNonInstantiability:
    def test_cannot_instantiate_base_directly(self):
        with pytest.raises(TypeError):
            BotInvokerBase()

    def test_subclass_missing_call_cannot_be_instantiated(self):
        class IncompleteInvoker(BotInvokerBase):
            pass

        with pytest.raises(TypeError):
            IncompleteInvoker()


class TestCallableContract:
    def test_call_signature_accepts_input_turns_thread_id(self):
        signature = inspect.signature(BotInvokerBase.__call__)
        params = list(signature.parameters)
        assert params == ["self", "input", "turns", "thread_id"]

    def test_concrete_subclass_is_callable_and_returns_turn(self):
        class EchoInvoker(BotInvokerBase):
            def __call__(self, input: str, turns: list[Turn], thread_id: str) -> Turn:
                return Turn(role="assistant", content=f"echo: {input}")

        invoker = EchoInvoker()
        result = invoker(input="hello", turns=[], thread_id="thread-1")

        assert isinstance(result, Turn)
        assert result.role == "assistant"
        assert result.content == "echo: hello"

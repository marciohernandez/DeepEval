"""Unit tests for LangChainBotInvoker (M4.1, T018). The resolved chain's native
.invoke() is mocked; no real LangChain graph execution occurs.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from deepeval.test_case import Turn
from langchain_core.messages import AIMessage

from deepeval_platform.synthetic.langchain_bot_invoker import LangChainBotInvoker

_TARGET = "tests.unit.synthetic._fixtures.fake_chain_module.chain"


class TestStringResultNormalization:
    def test_str_result_used_directly(self, mocker):
        chain = MagicMock()
        chain.invoke.return_value = "plain string answer"
        mocker.patch(
            "deepeval_platform.synthetic.langchain_bot_invoker.LangChainBotInvoker._resolve_chain",
            return_value=chain,
        )
        invoker = LangChainBotInvoker(bot_id="test_agent_bot", chain_target=_TARGET)

        turn = invoker(input="hi", turns=[], thread_id="t1")

        assert isinstance(turn, Turn)
        assert turn.content == "plain string answer"


class TestBaseMessageResultNormalization:
    def test_ai_message_content_extracted(self, mocker):
        chain = MagicMock()
        chain.invoke.return_value = AIMessage(content="J'adore la programmation.")
        mocker.patch(
            "deepeval_platform.synthetic.langchain_bot_invoker.LangChainBotInvoker._resolve_chain",
            return_value=chain,
        )
        invoker = LangChainBotInvoker(bot_id="test_agent_bot", chain_target=_TARGET)

        turn = invoker(input="hi", turns=[], thread_id="t1")

        assert turn.content == "J'adore la programmation."


class TestDictResultNormalization:
    @pytest.mark.parametrize("key", ["output", "text", "answer"])
    def test_first_non_empty_string_key_extracted(self, mocker, key):
        chain = MagicMock()
        chain.invoke.return_value = {key: "dict-based answer"}
        mocker.patch(
            "deepeval_platform.synthetic.langchain_bot_invoker.LangChainBotInvoker._resolve_chain",
            return_value=chain,
        )
        invoker = LangChainBotInvoker(bot_id="test_agent_bot", chain_target=_TARGET)

        turn = invoker(input="hi", turns=[], thread_id="t1")

        assert turn.content == "dict-based answer"

    def test_output_takes_precedence_over_text_and_answer(self, mocker):
        chain = MagicMock()
        chain.invoke.return_value = {"output": "from-output", "text": "from-text", "answer": "from-answer"}
        mocker.patch(
            "deepeval_platform.synthetic.langchain_bot_invoker.LangChainBotInvoker._resolve_chain",
            return_value=chain,
        )
        invoker = LangChainBotInvoker(bot_id="test_agent_bot", chain_target=_TARGET)

        turn = invoker(input="hi", turns=[], thread_id="t1")

        assert turn.content == "from-output"


class TestStructuredFailures:
    def test_resolution_failure_returns_bot_unreachable(self, mocker):
        mocker.patch(
            "deepeval_platform.synthetic.langchain_bot_invoker.LangChainBotInvoker._resolve_chain",
            side_effect=ImportError("no such module"),
        )
        invoker = LangChainBotInvoker(bot_id="test_agent_bot", chain_target="does.not.exist")

        turn = invoker(input="hi", turns=[], thread_id="t1")

        assert turn.content == "[BOT_UNREACHABLE]"
        assert turn.metadata["error"]["bot_id"] == "test_agent_bot"

    def test_invocation_failure_returns_bot_unreachable(self, mocker):
        chain = MagicMock()
        chain.invoke.side_effect = RuntimeError("chain exploded")
        mocker.patch(
            "deepeval_platform.synthetic.langchain_bot_invoker.LangChainBotInvoker._resolve_chain",
            return_value=chain,
        )
        invoker = LangChainBotInvoker(bot_id="test_agent_bot", chain_target=_TARGET)

        turn = invoker(input="hi", turns=[], thread_id="t1")

        assert turn.content == "[BOT_UNREACHABLE]"

    def test_empty_result_returns_bot_unreachable(self, mocker):
        chain = MagicMock()
        chain.invoke.return_value = ""
        mocker.patch(
            "deepeval_platform.synthetic.langchain_bot_invoker.LangChainBotInvoker._resolve_chain",
            return_value=chain,
        )
        invoker = LangChainBotInvoker(bot_id="test_agent_bot", chain_target=_TARGET)

        turn = invoker(input="hi", turns=[], thread_id="t1")

        assert turn.content == "[BOT_UNREACHABLE]"

    def test_malformed_result_type_returns_bot_unreachable(self, mocker):
        chain = MagicMock()
        chain.invoke.return_value = 12345
        mocker.patch(
            "deepeval_platform.synthetic.langchain_bot_invoker.LangChainBotInvoker._resolve_chain",
            return_value=chain,
        )
        invoker = LangChainBotInvoker(bot_id="test_agent_bot", chain_target=_TARGET)

        turn = invoker(input="hi", turns=[], thread_id="t1")

        assert turn.content == "[BOT_UNREACHABLE]"

    def test_dict_without_supported_keys_returns_bot_unreachable(self, mocker):
        chain = MagicMock()
        chain.invoke.return_value = {"unexpected": "shape"}
        mocker.patch(
            "deepeval_platform.synthetic.langchain_bot_invoker.LangChainBotInvoker._resolve_chain",
            return_value=chain,
        )
        invoker = LangChainBotInvoker(bot_id="test_agent_bot", chain_target=_TARGET)

        turn = invoker(input="hi", turns=[], thread_id="t1")

        assert turn.content == "[BOT_UNREACHABLE]"

    def test_never_raises(self, mocker):
        mocker.patch(
            "deepeval_platform.synthetic.langchain_bot_invoker.LangChainBotInvoker._resolve_chain",
            side_effect=RuntimeError("boom"),
        )
        invoker = LangChainBotInvoker(bot_id="test_agent_bot", chain_target=_TARGET)

        try:
            turn = invoker(input="hi", turns=[], thread_id="t1")
        except Exception as exc:  # pragma: no cover - failure path under test
            pytest.fail(f"Invoker must never raise, got: {exc}")

        assert turn.content == "[BOT_UNREACHABLE]"


class TestRealChainResolution:
    def test_real_dotted_path_resolves_and_invokes(self):
        """Exercises the real _resolve_chain implementation (no mocking of it)."""
        invoker = LangChainBotInvoker(
            bot_id="test_agent_bot",
            chain_target="tests.unit.synthetic._fixtures.fake_chain_module.chain",
        )

        turn = invoker(input="How do I reset my password?", turns=[], thread_id="t1")

        assert turn.content == "resolved chain answer for: How do I reset my password?"

    def test_real_resolution_failure_returns_bot_unreachable(self):
        invoker = LangChainBotInvoker(
            bot_id="test_agent_bot", chain_target="does.not.exist.chain"
        )

        turn = invoker(input="hi", turns=[], thread_id="t1")

        assert turn.content == "[BOT_UNREACHABLE]"
        assert turn.metadata["error"]["code"] == "resolution_error"


class TestNativeInvokeUsed:
    def test_invoke_called_with_plain_string_input(self, mocker):
        chain = MagicMock()
        chain.invoke.return_value = "ok"
        mocker.patch(
            "deepeval_platform.synthetic.langchain_bot_invoker.LangChainBotInvoker._resolve_chain",
            return_value=chain,
        )
        invoker = LangChainBotInvoker(bot_id="test_agent_bot", chain_target=_TARGET)

        invoker(input="How do I reset my password?", turns=[], thread_id="t1")

        chain.invoke.assert_called_once_with("How do I reset my password?")

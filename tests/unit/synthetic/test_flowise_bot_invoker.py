"""Unit tests for FlowiseBotInvoker (M4.1, T017). httpx is mocked; no network calls."""
from __future__ import annotations

from unittest.mock import MagicMock

import httpx
import pytest
from deepeval.test_case import Turn

from deepeval_platform.synthetic.flowise_bot_invoker import FlowiseBotInvoker


def _response(status_code=200, json_data=None, json_error=None):
    response = MagicMock(spec=httpx.Response)
    response.status_code = status_code
    if json_error is not None:
        response.json.side_effect = json_error
    else:
        response.json.return_value = json_data
    return response


class TestPayloadAndSession:
    def test_posts_question_and_session_id(self, mocker):
        post = mocker.patch(
            "deepeval_platform.synthetic.flowise_bot_invoker.httpx.post",
            return_value=_response(json_data={"text": "hello back"}),
        )
        invoker = FlowiseBotInvoker(bot_id="test_rag_bot", endpoint_url="https://flowise/api")

        invoker(input="How do I reset my password?", turns=[], thread_id="thread-123")

        _, kwargs = post.call_args
        assert post.call_args.args[0] == "https://flowise/api"
        payload = kwargs["json"]
        assert payload["question"] == "How do I reset my password?"
        assert payload["overrideConfig"]["sessionId"] == "thread-123"


class TestSuccessfulExtraction:
    def test_non_empty_text_extracted(self, mocker):
        mocker.patch(
            "deepeval_platform.synthetic.flowise_bot_invoker.httpx.post",
            return_value=_response(json_data={"text": "The password reset link is on the login page."}),
        )
        invoker = FlowiseBotInvoker(bot_id="test_rag_bot", endpoint_url="https://flowise/api")

        turn = invoker(input="reset password", turns=[], thread_id="t1")

        assert isinstance(turn, Turn)
        assert turn.role == "assistant"
        assert turn.content == "The password reset link is on the login page."


class TestFailureModes:
    def test_non_2xx_status_returns_bot_unreachable(self, mocker):
        mocker.patch(
            "deepeval_platform.synthetic.flowise_bot_invoker.httpx.post",
            return_value=_response(status_code=500, json_data={"text": "irrelevant"}),
        )
        invoker = FlowiseBotInvoker(bot_id="test_rag_bot", endpoint_url="https://flowise/api")

        turn = invoker(input="x", turns=[], thread_id="t1")

        assert turn.content == "[BOT_UNREACHABLE]"
        assert turn.metadata["error"]["bot_id"] == "test_rag_bot"

    def test_io_error_returns_bot_unreachable(self, mocker):
        mocker.patch(
            "deepeval_platform.synthetic.flowise_bot_invoker.httpx.post",
            side_effect=httpx.ConnectError("connection refused"),
        )
        invoker = FlowiseBotInvoker(bot_id="test_rag_bot", endpoint_url="https://flowise/api")

        turn = invoker(input="x", turns=[], thread_id="t1")

        assert turn.content == "[BOT_UNREACHABLE]"
        assert turn.metadata["error"]["type"] == "ConnectError"

    def test_malformed_json_returns_bot_unreachable(self, mocker):
        mocker.patch(
            "deepeval_platform.synthetic.flowise_bot_invoker.httpx.post",
            return_value=_response(json_error=ValueError("not json")),
        )
        invoker = FlowiseBotInvoker(bot_id="test_rag_bot", endpoint_url="https://flowise/api")

        turn = invoker(input="x", turns=[], thread_id="t1")

        assert turn.content == "[BOT_UNREACHABLE]"
        assert turn.metadata["error"]["code"] == "malformed_response"

    def test_missing_text_field_returns_bot_unreachable(self, mocker):
        mocker.patch(
            "deepeval_platform.synthetic.flowise_bot_invoker.httpx.post",
            return_value=_response(json_data={"unexpected": "shape"}),
        )
        invoker = FlowiseBotInvoker(bot_id="test_rag_bot", endpoint_url="https://flowise/api")

        turn = invoker(input="x", turns=[], thread_id="t1")

        assert turn.content == "[BOT_UNREACHABLE]"

    def test_empty_text_field_returns_bot_unreachable(self, mocker):
        mocker.patch(
            "deepeval_platform.synthetic.flowise_bot_invoker.httpx.post",
            return_value=_response(json_data={"text": ""}),
        )
        invoker = FlowiseBotInvoker(bot_id="test_rag_bot", endpoint_url="https://flowise/api")

        turn = invoker(input="x", turns=[], thread_id="t1")

        assert turn.content == "[BOT_UNREACHABLE]"

    def test_never_raises(self, mocker):
        mocker.patch(
            "deepeval_platform.synthetic.flowise_bot_invoker.httpx.post",
            side_effect=RuntimeError("unexpected failure"),
        )
        invoker = FlowiseBotInvoker(bot_id="test_rag_bot", endpoint_url="https://flowise/api")

        try:
            turn = invoker(input="x", turns=[], thread_id="t1")
        except Exception as exc:  # pragma: no cover - failure path under test
            pytest.fail(f"Invoker must never raise, got: {exc}")

        assert turn.content == "[BOT_UNREACHABLE]"

    def test_error_metadata_is_sanitized_structured_dict(self, mocker):
        mocker.patch(
            "deepeval_platform.synthetic.flowise_bot_invoker.httpx.post",
            side_effect=httpx.ConnectError("connection refused"),
        )
        invoker = FlowiseBotInvoker(bot_id="test_rag_bot", endpoint_url="https://flowise/api")

        turn = invoker(input="x", turns=[], thread_id="t1")

        error = turn.metadata["error"]
        assert set(error.keys()) == {"code", "type", "message", "bot_id"}
        assert isinstance(error["message"], str)

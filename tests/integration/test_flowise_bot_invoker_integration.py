"""Integration tests for FlowiseBotInvoker against a real local HTTP server
(M4.1, T021). No external credentials or network access are required.
"""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from deepeval_platform.synthetic.flowise_bot_invoker import FlowiseBotInvoker

_received_requests: list[dict] = []
_next_response: dict = {"status": 200, "body": {"text": "default response"}}


class _Handler(BaseHTTPRequestHandler):
    def do_POST(self):  # noqa: N802 - http.server naming convention
        length = int(self.headers.get("Content-Length", 0))
        raw_body = self.rfile.read(length)
        _received_requests.append(
            {"path": self.path, "body": json.loads(raw_body) if raw_body else {}}
        )

        status = _next_response["status"]
        body = _next_response["body"]
        self.send_response(status)
        if isinstance(body, (dict, list)):
            payload = json.dumps(body).encode("utf-8")
            self.send_header("Content-Type", "application/json")
        else:
            payload = body.encode("utf-8")
            self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format, *args):  # noqa: A002 - silence default logging
        pass


@pytest.fixture
def flowise_server():
    server = HTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    _received_requests.clear()
    _next_response["status"] = 200
    _next_response["body"] = {"text": "default response"}
    yield server
    server.shutdown()
    thread.join(timeout=5)


@pytest.mark.integration
class TestFlowiseBotInvokerIntegration:
    def test_real_http_request_and_session_propagation(self, flowise_server):
        port = flowise_server.server_address[1]
        _next_response["body"] = {"text": "Here is your refund status."}

        invoker = FlowiseBotInvoker(
            bot_id="test_rag_bot", endpoint_url=f"http://127.0.0.1:{port}/api/v1/prediction/x"
        )

        turn = invoker(input="Where is my refund?", turns=[], thread_id="session-abc")

        assert turn.content == "Here is your refund status."
        assert len(_received_requests) == 1
        body = _received_requests[0]["body"]
        assert body["question"] == "Where is my refund?"
        assert body["overrideConfig"]["sessionId"] == "session-abc"

    def test_non_2xx_response_normalized(self, flowise_server):
        port = flowise_server.server_address[1]
        _next_response["status"] = 500
        _next_response["body"] = {"text": "irrelevant"}

        invoker = FlowiseBotInvoker(
            bot_id="test_rag_bot", endpoint_url=f"http://127.0.0.1:{port}/api"
        )
        turn = invoker(input="x", turns=[], thread_id="t1")

        assert turn.content == "[BOT_UNREACHABLE]"
        assert turn.metadata["error"]["bot_id"] == "test_rag_bot"

    def test_malformed_response_normalized(self, flowise_server):
        port = flowise_server.server_address[1]
        _next_response["status"] = 200
        _next_response["body"] = "not-json-and-not-a-dict-either"

        invoker = FlowiseBotInvoker(
            bot_id="test_rag_bot", endpoint_url=f"http://127.0.0.1:{port}/api"
        )
        turn = invoker(input="x", turns=[], thread_id="t1")

        assert turn.content == "[BOT_UNREACHABLE]"

"""Integration tests for LangfuseClient (US2 — real Langfuse connection).

Prerequisites:
  - A running Langfuse instance reachable at LANGFUSE_HOST
  - LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY set in .env

After flush() returns, verify the submitted trace appears in the Langfuse
dashboard within 30 seconds (SC-007 latency SLA — manual verification only).
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from deepeval_platform.observability import LangfuseClient, TelemetryEvent


@pytest.fixture(autouse=True)
def reset_langfuse_singleton():
    """Reset singleton after every test to avoid cross-test leakage."""
    yield
    LangfuseClient._instance = None


@pytest.mark.integration
class TestLangfuseClientIntegration:
    def test_real_connection_established(self):
        """Singleton is created and SDK is connected when credentials are valid."""
        client = LangfuseClient.instance()
        assert client is not None
        assert client.is_connected() is True

    def test_submit_and_flush_without_error(self):
        """A synthetic TelemetryEvent can be submitted and flushed without raising."""
        client = LangfuseClient.instance()
        event = TelemetryEvent(
            session_id="integration-test-session",
            trace_id=None,
            name="integration-test-trace",
            input={"prompt": "Hello, world!"},
            output={"response": "Hi!"},
            metadata={"source": "integration-test"},
            start_time=datetime.now(timezone.utc),
            end_time=datetime.now(timezone.utc),
        )
        client.submit(event)
        client.flush()  # blocks until sent — must not raise

    def test_singleton_stable_across_multiple_calls(self):
        """instance() always returns the same object within a process."""
        c1 = LangfuseClient.instance()
        c2 = LangfuseClient.instance()
        c3 = LangfuseClient.instance()
        assert c1 is c2
        assert c2 is c3

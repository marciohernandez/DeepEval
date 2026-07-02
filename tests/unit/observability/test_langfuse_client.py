"""Unit tests for LangfuseClient (US2 — Reliable Observability Telemetry)."""
from __future__ import annotations

import logging
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from deepeval.observability.langfuse_client import (
    LangfuseClient,
    LangfuseError,
    TelemetryEvent,
)


@pytest.fixture(autouse=True)
def reset_langfuse_singleton():
    """Reset LangfuseClient singleton after every test."""
    yield
    LangfuseClient._instance = None


# ---------------------------------------------------------------------------
# TelemetryEvent
# ---------------------------------------------------------------------------

class TestTelemetryEvent:
    def test_creation_with_all_fields(self):
        start = datetime(2026, 1, 1)
        end = datetime(2026, 1, 2)
        event = TelemetryEvent(
            session_id="sess-001",
            trace_id="trace-001",
            name="test-trace",
            input={"query": "hello"},
            output={"response": "hi"},
            metadata={"bot": "test"},
            start_time=start,
            end_time=end,
        )
        assert event.session_id == "sess-001"
        assert event.trace_id == "trace-001"
        assert event.name == "test-trace"
        assert event.input == {"query": "hello"}
        assert event.output == {"response": "hi"}
        assert event.metadata == {"bot": "test"}
        assert event.start_time == start
        assert event.end_time == end

    def test_creation_with_optional_fields_none(self):
        event = TelemetryEvent(
            session_id="sess-001",
            trace_id=None,
            name="test-trace",
            input=None,
            output=None,
            metadata={},
            start_time=None,
            end_time=None,
        )
        assert event.trace_id is None
        assert event.input is None
        assert event.output is None
        assert event.start_time is None
        assert event.end_time is None

    def test_input_can_be_string(self):
        event = TelemetryEvent(
            session_id="s", trace_id=None, name="n",
            input="plain text input", output=None,
            metadata={}, start_time=None, end_time=None,
        )
        assert event.input == "plain text input"


# ---------------------------------------------------------------------------
# Singleton behaviour
# ---------------------------------------------------------------------------

class TestLangfuseClientSingleton:
    def test_instance_returns_same_object(self, mock_config):
        with patch("deepeval.observability.langfuse_client.Langfuse"):
            with patch("atexit.register"):
                c1 = LangfuseClient.instance()
                c2 = LangfuseClient.instance()
                assert c1 is c2

    def test_sdk_initialized_only_once(self, mock_config):
        with patch("deepeval.observability.langfuse_client.Langfuse") as mock_sdk:
            with patch("atexit.register"):
                LangfuseClient.instance()
                LangfuseClient.instance()
                mock_sdk.assert_called_once()

    def test_atexit_registered_exactly_once(self, mock_config):
        with patch("deepeval.observability.langfuse_client.Langfuse"):
            with patch("atexit.register") as mock_atexit:
                LangfuseClient.instance()
                LangfuseClient.instance()
                mock_atexit.assert_called_once()


# ---------------------------------------------------------------------------
# is_connected()
# ---------------------------------------------------------------------------

class TestIsConnected:
    def test_true_after_successful_init(self, mock_config):
        with patch("deepeval.observability.langfuse_client.Langfuse"):
            with patch("atexit.register"):
                client = LangfuseClient.instance()
                assert client.is_connected() is True

    def test_false_when_sdk_raises_at_init(self, mock_config):
        with patch("deepeval.observability.langfuse_client.Langfuse", side_effect=Exception("conn err")):
            with patch("atexit.register"):
                client = LangfuseClient.instance()
                assert client.is_connected() is False

    def test_warning_logged_when_sdk_raises_at_init(self, mock_config, caplog):
        with patch("deepeval.observability.langfuse_client.Langfuse", side_effect=Exception("conn err")):
            with patch("atexit.register"):
                with caplog.at_level(logging.WARNING):
                    LangfuseClient.instance()
                assert any(r.levelno >= logging.WARNING for r in caplog.records)

    def test_no_exception_raised_when_sdk_raises_at_init(self, mock_config):
        with patch("deepeval.observability.langfuse_client.Langfuse", side_effect=Exception("conn err")):
            with patch("atexit.register"):
                client = LangfuseClient.instance()  # must not raise
                assert client is not None


# ---------------------------------------------------------------------------
# submit()
# ---------------------------------------------------------------------------

class TestSubmit:
    def _make_event(self, **overrides) -> TelemetryEvent:
        defaults = dict(
            session_id="sess-001",
            trace_id="trace-001",
            name="test-trace",
            input={"q": "hello"},
            output={"a": "hi"},
            metadata={},
            start_time=None,
            end_time=None,
        )
        defaults.update(overrides)
        return TelemetryEvent(**defaults)

    def test_submit_calls_sdk_batch(self, mock_config):
        mock_sdk = MagicMock()
        with patch("deepeval.observability.langfuse_client.Langfuse", return_value=mock_sdk):
            with patch("atexit.register"):
                client = LangfuseClient.instance()
                client.submit(self._make_event())
                mock_sdk.api.ingestion.batch.assert_called_once()

    def test_submit_passes_correct_fields(self, mock_config):
        mock_sdk = MagicMock()
        start = datetime(2026, 1, 1)
        with patch("deepeval.observability.langfuse_client.Langfuse", return_value=mock_sdk):
            with patch("atexit.register"):
                client = LangfuseClient.instance()
                event = self._make_event(
                    session_id="sess-999",
                    trace_id="trace-999",
                    name="my-trace",
                    input={"q": "hi"},
                    output={"a": "ho"},
                    metadata={"bot": "tester"},
                    start_time=start,
                )
                client.submit(event)
                mock_sdk.api.ingestion.batch.assert_called_once()
                call_batch = mock_sdk.api.ingestion.batch.call_args.kwargs["batch"]
                assert len(call_batch) == 1
                body = call_batch[0].body
                assert body.id == "trace-999"
                assert body.name == "my-trace"
                assert body.session_id == "sess-999"
                assert body.input == {"q": "hi"}
                assert body.output == {"a": "ho"}
                assert body.metadata == {"bot": "tester"}
                assert body.timestamp == start

    def test_submit_warning_logged_when_sdk_raises(self, mock_config, caplog):
        mock_sdk = MagicMock()
        mock_sdk.api.ingestion.batch.side_effect = Exception("SDK boom")
        with patch("deepeval.observability.langfuse_client.Langfuse", return_value=mock_sdk):
            with patch("atexit.register"):
                with caplog.at_level(logging.WARNING):
                    client = LangfuseClient.instance()
                    client.submit(self._make_event())
                assert any(r.levelno >= logging.WARNING for r in caplog.records)

    def test_submit_no_exception_when_sdk_raises(self, mock_config):
        mock_sdk = MagicMock()
        mock_sdk.api.ingestion.batch.side_effect = Exception("SDK boom")
        with patch("deepeval.observability.langfuse_client.Langfuse", return_value=mock_sdk):
            with patch("atexit.register"):
                client = LangfuseClient.instance()
                client.submit(self._make_event())  # must not raise

    def test_submit_noop_when_not_connected(self, mock_config, caplog):
        """When SDK failed to init, submit logs WARNING and returns without SDK call."""
        mock_sdk = MagicMock()
        with patch("deepeval.observability.langfuse_client.Langfuse", side_effect=Exception("init err")):
            with patch("atexit.register"):
                with caplog.at_level(logging.WARNING):
                    client = LangfuseClient.instance()
                    assert client.is_connected() is False
                    client.submit(self._make_event())  # must not raise
                assert any(r.levelno >= logging.WARNING for r in caplog.records)
        mock_sdk.api.ingestion.batch.assert_not_called()


# ---------------------------------------------------------------------------
# flush()
# ---------------------------------------------------------------------------

class TestFlush:
    def test_flush_calls_sdk_flush(self, mock_config):
        mock_sdk = MagicMock()
        with patch("deepeval.observability.langfuse_client.Langfuse", return_value=mock_sdk):
            with patch("atexit.register"):
                client = LangfuseClient.instance()
                client.flush()
                mock_sdk.flush.assert_called_once()

    def test_flush_noop_when_not_connected(self, mock_config):
        """flush() must not raise when SDK never initialized."""
        with patch("deepeval.observability.langfuse_client.Langfuse", side_effect=Exception("init err")):
            with patch("atexit.register"):
                client = LangfuseClient.instance()
                client.flush()  # must not raise


# ---------------------------------------------------------------------------
# LangfuseError
# ---------------------------------------------------------------------------

class TestLangfuseError:
    def test_is_exception_subclass(self):
        assert issubclass(LangfuseError, Exception)

    def test_can_be_instantiated_with_message(self):
        err = LangfuseError("something went wrong")
        assert str(err) == "something went wrong"

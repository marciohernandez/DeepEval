"""Unit tests for TraceRepository (US5 — Trace Extraction for Evaluation Input)."""
from __future__ import annotations

import json
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from deepeval_platform.repositories.models import TraceRecord
from deepeval_platform.repositories.trace_repository import TraceRepository, TraceRepositoryError


def _make_raw_trace(**overrides) -> dict:
    trace = {
        "id": "trace-001",
        "sessionId": "sess-001",
        "tags": ["my-bot"],
        "input": {"text": "hello"},
        "output": {"text": "world"},
        "metadata": {"source": "test"},
        "timestamp": "2026-01-01T12:00:00",
    }
    trace.update(overrides)
    return trace


def _mock_urlopen(traces: list) -> MagicMock:
    """Return a MagicMock that behaves as a urllib context-manager response."""
    body = json.dumps({"data": traces}).encode()
    resp = MagicMock()
    resp.read.return_value = body
    resp.__enter__ = lambda s: s
    resp.__exit__ = lambda s, *a: False
    return resp


# ---------------------------------------------------------------------------
# get_by_bot
# ---------------------------------------------------------------------------

class TestGetByBot:
    def test_returns_list_of_trace_records(self, mock_config):
        with patch("urllib.request.urlopen", return_value=_mock_urlopen([_make_raw_trace()])):
            results = TraceRepository().get_by_bot("my-bot")
        assert len(results) == 1
        assert isinstance(results[0], TraceRecord)

    def test_all_entity_fields_populated(self, mock_config):
        with patch("urllib.request.urlopen", return_value=_mock_urlopen([_make_raw_trace()])):
            results = TraceRepository().get_by_bot("my-bot")
        t = results[0]
        assert t.trace_id == "trace-001"
        assert t.session_id == "sess-001"
        assert t.bot_id == "my-bot"
        assert t.input == {"text": "hello"}
        assert t.output == {"text": "world"}
        assert t.metadata == {"source": "test"}
        assert t.start_time == datetime(2026, 1, 1, 12, 0, 0)

    def test_passes_tags_to_request_url(self, mock_config):
        with patch("urllib.request.urlopen", return_value=_mock_urlopen([])) as mock_open:
            TraceRepository().get_by_bot("customer-support")
        url = mock_open.call_args[0][0].full_url
        assert "customer-support" in url

    def test_empty_result_returns_empty_list(self, mock_config):
        with patch("urllib.request.urlopen", return_value=_mock_urlopen([])):
            results = TraceRepository().get_by_bot("no-such-bot")
        assert results == []

    def test_raw_langfuse_objects_not_returned(self, mock_config):
        with patch("urllib.request.urlopen", return_value=_mock_urlopen([_make_raw_trace()])):
            results = TraceRepository().get_by_bot("my-bot")
        for item in results:
            assert isinstance(item, TraceRecord)

    def test_http_error_propagates_as_trace_repository_error(self, mock_config):
        with patch("urllib.request.urlopen", side_effect=Exception("HTTP error")):
            with pytest.raises(TraceRepositoryError):
                TraceRepository().get_by_bot("my-bot")


# ---------------------------------------------------------------------------
# get_by_session
# ---------------------------------------------------------------------------

class TestGetBySession:
    def test_returns_list_of_trace_records(self, mock_config):
        with patch("urllib.request.urlopen", return_value=_mock_urlopen([_make_raw_trace()])):
            results = TraceRepository().get_by_session("sess-001")
        assert len(results) == 1
        assert isinstance(results[0], TraceRecord)

    def test_returns_matching_traces(self, mock_config):
        raw = _make_raw_trace(sessionId="sess-abc")
        with patch("urllib.request.urlopen", return_value=_mock_urlopen([raw])):
            results = TraceRepository().get_by_session("sess-abc")
        assert results[0].session_id == "sess-abc"

    def test_passes_session_id_to_request_url(self, mock_config):
        with patch("urllib.request.urlopen", return_value=_mock_urlopen([])) as mock_open:
            TraceRepository().get_by_session("my-session")
        url = mock_open.call_args[0][0].full_url
        assert "my-session" in url

    def test_empty_result_returns_empty_list(self, mock_config):
        with patch("urllib.request.urlopen", return_value=_mock_urlopen([])):
            results = TraceRepository().get_by_session("nonexistent-session")
        assert results == []

    def test_raw_langfuse_objects_not_returned(self, mock_config):
        with patch("urllib.request.urlopen", return_value=_mock_urlopen([_make_raw_trace()])):
            results = TraceRepository().get_by_session("sess-001")
        for item in results:
            assert isinstance(item, TraceRecord)

    def test_output_none_handled_for_interrupted_sessions(self, mock_config):
        raw = _make_raw_trace(output=None)
        with patch("urllib.request.urlopen", return_value=_mock_urlopen([raw])):
            results = TraceRepository().get_by_session("sess-001")
        assert results[0].output is None

    def test_http_error_propagates_as_trace_repository_error(self, mock_config):
        with patch("urllib.request.urlopen", side_effect=Exception("HTTP error")):
            with pytest.raises(TraceRepositoryError):
                TraceRepository().get_by_session("sess-001")


# ---------------------------------------------------------------------------
# get_by_date_range
# ---------------------------------------------------------------------------

class TestGetByDateRange:
    def test_returns_list_of_trace_records(self, mock_config):
        start, end = datetime(2026, 1, 1), datetime(2026, 1, 31)
        with patch("urllib.request.urlopen", return_value=_mock_urlopen([_make_raw_trace()])):
            results = TraceRepository().get_by_date_range("my-bot", start, end)
        assert len(results) == 1
        assert isinstance(results[0], TraceRecord)

    def test_passes_timestamps_to_request_url(self, mock_config):
        start, end = datetime(2026, 1, 1), datetime(2026, 1, 31)
        with patch("urllib.request.urlopen", return_value=_mock_urlopen([])) as mock_open:
            TraceRepository().get_by_date_range("my-bot", start, end)
        url = mock_open.call_args[0][0].full_url
        assert "fromTimestamp" in url
        assert "toTimestamp" in url

    def test_passes_bot_id_as_tag_to_request_url(self, mock_config):
        start, end = datetime(2026, 1, 1), datetime(2026, 1, 31)
        with patch("urllib.request.urlopen", return_value=_mock_urlopen([])) as mock_open:
            TraceRepository().get_by_date_range("my-bot", start, end)
        url = mock_open.call_args[0][0].full_url
        assert "my-bot" in url

    def test_empty_result_returns_empty_list(self, mock_config):
        start, end = datetime(2026, 1, 1), datetime(2026, 1, 31)
        with patch("urllib.request.urlopen", return_value=_mock_urlopen([])):
            results = TraceRepository().get_by_date_range("my-bot", start, end)
        assert results == []

    def test_raw_langfuse_objects_not_returned(self, mock_config):
        start, end = datetime(2026, 1, 1), datetime(2026, 1, 31)
        with patch("urllib.request.urlopen", return_value=_mock_urlopen([_make_raw_trace()])):
            results = TraceRepository().get_by_date_range("my-bot", start, end)
        for item in results:
            assert isinstance(item, TraceRecord)

    def test_http_error_propagates_as_trace_repository_error(self, mock_config):
        start, end = datetime(2026, 1, 1), datetime(2026, 1, 31)
        with patch("urllib.request.urlopen", side_effect=Exception("HTTP error")):
            with pytest.raises(TraceRepositoryError):
                TraceRepository().get_by_date_range("my-bot", start, end)


# ---------------------------------------------------------------------------
# TraceRepositoryError
# ---------------------------------------------------------------------------

class TestTraceRepositoryError:
    def test_is_exception_subclass(self):
        assert issubclass(TraceRepositoryError, Exception)

    def test_can_be_instantiated_with_message(self):
        err = TraceRepositoryError("connection failed")
        assert str(err) == "connection failed"

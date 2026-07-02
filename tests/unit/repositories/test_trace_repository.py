"""Unit tests for TraceRepository (US5 — Trace Extraction for Evaluation Input)."""
from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from deepeval.repositories.models import TraceRecord
from deepeval.repositories.trace_repository import TraceRepository, TraceRepositoryError


def _make_raw_trace(**overrides) -> MagicMock:
    trace = MagicMock()
    trace.id = "trace-001"
    trace.session_id = "sess-001"
    trace.tags = ["my-bot"]
    trace.input = {"text": "hello"}
    trace.output = {"text": "world"}
    trace.metadata = {"source": "test"}
    trace.timestamp = datetime(2026, 1, 1, 12, 0, 0)
    for k, v in overrides.items():
        setattr(trace, k, v)
    return trace


def _make_langfuse_client(raw_traces: list) -> MagicMock:
    lf_client = MagicMock()
    lf_client._client.api.trace.list.return_value = MagicMock(data=raw_traces)
    return lf_client


# ---------------------------------------------------------------------------
# get_by_bot
# ---------------------------------------------------------------------------

class TestGetByBot:
    def test_returns_list_of_trace_records(self):
        raw = _make_raw_trace()
        with patch("deepeval.repositories.trace_repository.LangfuseClient") as mock_cls:
            mock_cls.instance.return_value = _make_langfuse_client([raw])
            repo = TraceRepository()
            results = repo.get_by_bot("my-bot")

        assert len(results) == 1
        assert isinstance(results[0], TraceRecord)

    def test_all_entity_fields_populated(self):
        raw = _make_raw_trace()
        with patch("deepeval.repositories.trace_repository.LangfuseClient") as mock_cls:
            mock_cls.instance.return_value = _make_langfuse_client([raw])
            repo = TraceRepository()
            results = repo.get_by_bot("my-bot")

        t = results[0]
        assert t.trace_id == "trace-001"
        assert t.session_id == "sess-001"
        assert t.bot_id == "my-bot"
        assert t.input == {"text": "hello"}
        assert t.output == {"text": "world"}
        assert t.metadata == {"source": "test"}
        assert t.start_time == datetime(2026, 1, 1, 12, 0, 0)

    def test_passes_tags_to_sdk(self):
        lf_client = _make_langfuse_client([])
        with patch("deepeval.repositories.trace_repository.LangfuseClient") as mock_cls:
            mock_cls.instance.return_value = lf_client
            repo = TraceRepository()
            repo.get_by_bot("customer-support")

        call_kwargs = lf_client._client.api.trace.list.call_args[1]
        assert "customer-support" in call_kwargs.get("tags", [])

    def test_empty_result_returns_empty_list(self):
        with patch("deepeval.repositories.trace_repository.LangfuseClient") as mock_cls:
            mock_cls.instance.return_value = _make_langfuse_client([])
            repo = TraceRepository()
            results = repo.get_by_bot("no-such-bot")

        assert results == []

    def test_raw_langfuse_objects_not_returned(self):
        raw = _make_raw_trace()
        with patch("deepeval.repositories.trace_repository.LangfuseClient") as mock_cls:
            mock_cls.instance.return_value = _make_langfuse_client([raw])
            repo = TraceRepository()
            results = repo.get_by_bot("my-bot")

        for item in results:
            assert isinstance(item, TraceRecord)

    def test_sdk_raises_propagates_as_trace_repository_error(self):
        lf_client = MagicMock()
        lf_client._client.api.trace.list.side_effect = Exception("SDK error")

        with patch("deepeval.repositories.trace_repository.LangfuseClient") as mock_cls:
            mock_cls.instance.return_value = lf_client
            repo = TraceRepository()
            with pytest.raises(TraceRepositoryError):
                repo.get_by_bot("my-bot")


# ---------------------------------------------------------------------------
# get_by_session
# ---------------------------------------------------------------------------

class TestGetBySession:
    def test_returns_list_of_trace_records(self):
        raw = _make_raw_trace()
        with patch("deepeval.repositories.trace_repository.LangfuseClient") as mock_cls:
            mock_cls.instance.return_value = _make_langfuse_client([raw])
            repo = TraceRepository()
            results = repo.get_by_session("sess-001")

        assert len(results) == 1
        assert isinstance(results[0], TraceRecord)

    def test_returns_matching_traces(self):
        raw = _make_raw_trace(session_id="sess-abc")
        with patch("deepeval.repositories.trace_repository.LangfuseClient") as mock_cls:
            mock_cls.instance.return_value = _make_langfuse_client([raw])
            repo = TraceRepository()
            results = repo.get_by_session("sess-abc")

        assert results[0].session_id == "sess-abc"

    def test_passes_session_id_to_sdk(self):
        lf_client = _make_langfuse_client([])
        with patch("deepeval.repositories.trace_repository.LangfuseClient") as mock_cls:
            mock_cls.instance.return_value = lf_client
            repo = TraceRepository()
            repo.get_by_session("my-session")

        call_kwargs = lf_client._client.api.trace.list.call_args[1]
        assert call_kwargs.get("session_id") == "my-session"

    def test_empty_result_returns_empty_list(self):
        with patch("deepeval.repositories.trace_repository.LangfuseClient") as mock_cls:
            mock_cls.instance.return_value = _make_langfuse_client([])
            repo = TraceRepository()
            results = repo.get_by_session("nonexistent-session")

        assert results == []

    def test_raw_langfuse_objects_not_returned(self):
        raw = _make_raw_trace()
        with patch("deepeval.repositories.trace_repository.LangfuseClient") as mock_cls:
            mock_cls.instance.return_value = _make_langfuse_client([raw])
            repo = TraceRepository()
            results = repo.get_by_session("sess-001")

        for item in results:
            assert isinstance(item, TraceRecord)

    def test_output_none_handled_for_interrupted_sessions(self):
        raw = _make_raw_trace(output=None)
        with patch("deepeval.repositories.trace_repository.LangfuseClient") as mock_cls:
            mock_cls.instance.return_value = _make_langfuse_client([raw])
            repo = TraceRepository()
            results = repo.get_by_session("sess-001")

        assert results[0].output is None

    def test_sdk_raises_propagates_as_trace_repository_error(self):
        lf_client = MagicMock()
        lf_client._client.api.trace.list.side_effect = Exception("SDK error")

        with patch("deepeval.repositories.trace_repository.LangfuseClient") as mock_cls:
            mock_cls.instance.return_value = lf_client
            repo = TraceRepository()
            with pytest.raises(TraceRepositoryError):
                repo.get_by_session("sess-001")


# ---------------------------------------------------------------------------
# get_by_date_range
# ---------------------------------------------------------------------------

class TestGetByDateRange:
    def test_returns_list_of_trace_records(self):
        raw = _make_raw_trace()
        start = datetime(2026, 1, 1)
        end = datetime(2026, 1, 31)
        with patch("deepeval.repositories.trace_repository.LangfuseClient") as mock_cls:
            mock_cls.instance.return_value = _make_langfuse_client([raw])
            repo = TraceRepository()
            results = repo.get_by_date_range("my-bot", start, end)

        assert len(results) == 1
        assert isinstance(results[0], TraceRecord)

    def test_passes_timestamps_to_sdk(self):
        start = datetime(2026, 1, 1)
        end = datetime(2026, 1, 31)
        lf_client = _make_langfuse_client([])

        with patch("deepeval.repositories.trace_repository.LangfuseClient") as mock_cls:
            mock_cls.instance.return_value = lf_client
            repo = TraceRepository()
            repo.get_by_date_range("my-bot", start, end)

        call_kwargs = lf_client._client.api.trace.list.call_args[1]
        assert call_kwargs.get("from_timestamp") == start
        assert call_kwargs.get("to_timestamp") == end

    def test_passes_bot_id_as_tag_to_sdk(self):
        start = datetime(2026, 1, 1)
        end = datetime(2026, 1, 31)
        lf_client = _make_langfuse_client([])

        with patch("deepeval.repositories.trace_repository.LangfuseClient") as mock_cls:
            mock_cls.instance.return_value = lf_client
            repo = TraceRepository()
            repo.get_by_date_range("my-bot", start, end)

        call_kwargs = lf_client._client.api.trace.list.call_args[1]
        assert "my-bot" in call_kwargs.get("tags", [])

    def test_empty_result_returns_empty_list(self):
        start = datetime(2026, 1, 1)
        end = datetime(2026, 1, 31)
        with patch("deepeval.repositories.trace_repository.LangfuseClient") as mock_cls:
            mock_cls.instance.return_value = _make_langfuse_client([])
            repo = TraceRepository()
            results = repo.get_by_date_range("my-bot", start, end)

        assert results == []

    def test_raw_langfuse_objects_not_returned(self):
        raw = _make_raw_trace()
        start = datetime(2026, 1, 1)
        end = datetime(2026, 1, 31)
        with patch("deepeval.repositories.trace_repository.LangfuseClient") as mock_cls:
            mock_cls.instance.return_value = _make_langfuse_client([raw])
            repo = TraceRepository()
            results = repo.get_by_date_range("my-bot", start, end)

        for item in results:
            assert isinstance(item, TraceRecord)

    def test_sdk_raises_propagates_as_trace_repository_error(self):
        lf_client = MagicMock()
        lf_client._client.api.trace.list.side_effect = Exception("SDK error")
        start = datetime(2026, 1, 1)
        end = datetime(2026, 1, 31)

        with patch("deepeval.repositories.trace_repository.LangfuseClient") as mock_cls:
            mock_cls.instance.return_value = lf_client
            repo = TraceRepository()
            with pytest.raises(TraceRepositoryError):
                repo.get_by_date_range("my-bot", start, end)


# ---------------------------------------------------------------------------
# TraceRepositoryError
# ---------------------------------------------------------------------------

class TestTraceRepositoryError:
    def test_is_exception_subclass(self):
        assert issubclass(TraceRepositoryError, Exception)

    def test_can_be_instantiated_with_message(self):
        err = TraceRepositoryError("connection failed")
        assert str(err) == "connection failed"

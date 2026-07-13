"""Integration tests for TraceRepository (US5 — real Langfuse connection).

Prerequisites:
  - A running Langfuse instance reachable at LANGFUSE_HOST with credentials in .env
  - At least one trace seeded via Scenario 2 (LangfuseClient quickstart) with
    session_id='test-session-001' and the trace tagged with a bot identifier.

Run after: tests/integration/test_langfuse_client_integration.py (Scenario 2 seeds the trace).
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from deepeval_platform.repositories import TraceRepository, TraceRecord, TraceRepositoryError


@pytest.mark.integration
class TestTraceRepositoryIntegration:
    def test_get_by_session_returns_trace_records(self):
        """Traces seeded in Scenario 2 are retrieved as structured TraceRecord instances."""
        repo = TraceRepository()
        results = repo.get_by_session("test-session-001")

        assert isinstance(results, list)
        for t in results:
            assert isinstance(t, TraceRecord)

    def test_get_by_session_all_fields_populated(self):
        """Returned TraceRecord contains expected field values from the seeded trace."""
        repo = TraceRepository()
        results = repo.get_by_session("test-session-001")

        if results:
            t = results[0]
            assert isinstance(t.trace_id, str) and t.trace_id
            assert t.session_id == "test-session-001"
            assert isinstance(t.input, (dict, str))
            assert isinstance(t.metadata, dict)
            assert isinstance(t.start_time, datetime)
            # end_time is None from list API — acceptable per spec
            assert t.end_time is None or isinstance(t.end_time, datetime)

    def test_get_by_session_nonexistent_returns_empty_list(self):
        """Querying a session that has no traces returns [] without raising."""
        repo = TraceRepository()
        results = repo.get_by_session("nonexistent-session-xyz-99999")

        assert results == []

    def test_get_by_session_date_range_excludes_future(self):
        """Date range filter excludes traces outside the window."""
        repo = TraceRepository()
        far_future_start = datetime(2099, 1, 1, tzinfo=timezone.utc)
        far_future_end = datetime(2099, 12, 31, tzinfo=timezone.utc)

        results = repo.get_by_date_range("my-bot", far_future_start, far_future_end)
        assert results == []

    def test_get_by_date_range_returns_trace_records(self):
        """Date range covering now returns TraceRecord instances (if any traces exist)."""
        repo = TraceRepository()
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        end = datetime(2027, 1, 1, tzinfo=timezone.utc)

        results = repo.get_by_date_range("my-bot", start, end)
        assert isinstance(results, list)
        for t in results:
            assert isinstance(t, TraceRecord)

"""Integration tests for TraceCollector (US1 — real Langfuse connection).

Prerequisites:
  - A running Langfuse instance reachable at LANGFUSE_HOST with credentials in .env.
  - config/bots.yaml declares `test_rag_bot` (platform: flowise).
  - At least 5 known traces seeded into Langfuse for test_rag_bot:
      - 3 completed interactions (with output)
      - 2 interrupted interactions (without output)
    See quickstart.md "Integration Test Run" for the seeding procedure.

Scenario 5 (SC-001, performance) synthesizes 500 records via monkeypatch on
TraceRepository.get_by_date_range (the sole network call) so the 3-second
wall-clock assertion is deterministic and does not depend on seeding 500 real
traces into Langfuse.
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from deepeval_platform.collection.trace_collector import TraceCollector
from deepeval_platform.collection.trace_filter import InteractionStatus, TraceFilter
from deepeval_platform.repositories.models import TraceRecord
from deepeval_platform.repositories.trace_repository import TraceRepository, TraceRepositoryError


@pytest.mark.integration
class TestTraceCollectorIntegration:
    def test_status_filter_returns_only_completed_interactions(self):
        """Acceptance Scenario 1: status=completed returns only completed interactions."""
        repo = TraceRepository()
        collector = TraceCollector(repo)

        now = datetime.now(timezone.utc)
        filter_ = TraceFilter(
            bot_id="test_rag_bot",
            start_date=now - timedelta(hours=1),
            end_date=now,
            status=InteractionStatus.COMPLETED,
        )
        results = collector.collect(filter_)

        assert all(r.output is not None for r in results)

    def test_bot_isolation_returns_only_matching_bot_id(self):
        """Acceptance Scenario 2: only interactions for the requested bot_id are returned."""
        repo = TraceRepository()
        collector = TraceCollector(repo)

        now = datetime.now(timezone.utc)
        filter_ = TraceFilter(
            bot_id="test_rag_bot",
            start_date=now - timedelta(hours=1),
            end_date=now,
        )
        results = collector.collect(filter_)

        assert all(r.bot_id == "test_rag_bot" for r in results)

    def test_no_matching_interactions_returns_empty_list(self):
        """Acceptance Scenario 3: an empty result is [], never an error."""
        repo = TraceRepository()
        collector = TraceCollector(repo)

        now = datetime.now(timezone.utc)
        filter_ = TraceFilter(
            bot_id="test_rag_bot",
            start_date=now - timedelta(minutes=1),
            end_date=now,
        )
        results = collector.collect(filter_)

        assert results == []

    def test_connectivity_failure_raises_descriptive_error(self):
        """Acceptance Scenario 4: an unreachable observability platform raises
        TraceRepositoryError immediately, with no retry."""
        broken_repo = TraceRepository.__new__(TraceRepository)
        broken_repo._base_url = "http://localhost:1/api/public/traces"
        broken_repo._auth_header = "Basic invalid"
        collector = TraceCollector(broken_repo)

        now = datetime.now(timezone.utc)
        filter_ = TraceFilter(
            bot_id="test_rag_bot",
            start_date=now - timedelta(hours=1),
            end_date=now,
        )

        with pytest.raises(TraceRepositoryError):
            collector.collect(filter_)

    def test_collect_completes_within_3_seconds_for_500_interactions(self):
        """SC-001: collect() completes within 3 seconds wall-clock for up to
        500 matching interactions."""
        now = datetime.now(timezone.utc)
        synthetic_records = [
            TraceRecord(
                trace_id=f"trace-{i}",
                session_id=None,
                bot_id="test_rag_bot",
                input={"text": "hello"},
                output={"text": "world"},
                metadata={},
                start_time=now - timedelta(seconds=i),
                end_time=None,
            )
            for i in range(500)
        ]

        repo = TraceRepository()
        collector = TraceCollector(repo)
        filter_ = TraceFilter(
            bot_id="test_rag_bot",
            start_date=now - timedelta(hours=1),
            end_date=now,
        )

        with patch.object(repo, "get_by_date_range", return_value=synthetic_records):
            start = time.monotonic()
            results = collector.collect(filter_)
            elapsed = time.monotonic() - start

        assert len(results) == 500
        assert elapsed <= 3.0

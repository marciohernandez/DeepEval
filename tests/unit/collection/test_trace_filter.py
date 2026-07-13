"""Unit tests for InteractionStatus and TraceFilter (US1 — Trace Collection)."""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from deepeval_platform.collection.trace_filter import InteractionStatus, TraceFilter


# ---------------------------------------------------------------------------
# InteractionStatus
# ---------------------------------------------------------------------------

class TestInteractionStatus:
    def test_completed_value(self):
        assert InteractionStatus.COMPLETED.value == "completed"

    def test_interrupted_value(self):
        assert InteractionStatus.INTERRUPTED.value == "interrupted"


# ---------------------------------------------------------------------------
# TraceFilter — valid construction
# ---------------------------------------------------------------------------

class TestTraceFilterValidConstruction:
    def test_valid_construction_without_status(self):
        start = datetime(2026, 1, 1)
        end = datetime(2026, 1, 2)
        f = TraceFilter(bot_id="my-bot", start_date=start, end_date=end)
        assert f.bot_id == "my-bot"
        assert f.start_date == start
        assert f.end_date == end
        assert f.status is None

    def test_valid_construction_with_status(self):
        start = datetime(2026, 1, 1)
        end = datetime(2026, 1, 2)
        f = TraceFilter(
            bot_id="my-bot",
            start_date=start,
            end_date=end,
            status=InteractionStatus.COMPLETED,
        )
        assert f.status == InteractionStatus.COMPLETED

    def test_is_frozen(self):
        f = TraceFilter(
            bot_id="my-bot",
            start_date=datetime(2026, 1, 1),
            end_date=datetime(2026, 1, 2),
        )
        with pytest.raises(Exception):
            f.bot_id = "other-bot"


# ---------------------------------------------------------------------------
# TraceFilter — invariants
# ---------------------------------------------------------------------------

class TestTraceFilterInvariants:
    def test_start_date_equal_end_date_raises(self):
        same = datetime(2026, 1, 1, 12, 0, 0)
        with pytest.raises(ValueError):
            TraceFilter(bot_id="my-bot", start_date=same, end_date=same)

    def test_start_date_after_end_date_raises(self):
        start = datetime(2026, 1, 2)
        end = datetime(2026, 1, 1)
        with pytest.raises(ValueError):
            TraceFilter(bot_id="my-bot", start_date=start, end_date=end)

    def test_empty_bot_id_raises(self):
        with pytest.raises(ValueError):
            TraceFilter(
                bot_id="",
                start_date=datetime(2026, 1, 1),
                end_date=datetime(2026, 1, 2),
            )

    def test_start_date_slightly_before_end_date_is_valid(self):
        start = datetime(2026, 1, 1)
        end = start + timedelta(microseconds=1)
        f = TraceFilter(bot_id="my-bot", start_date=start, end_date=end)
        assert f.start_date < f.end_date

"""Unit tests for FlowiseExtractor (US1 — Trace Collection)."""
from __future__ import annotations

from datetime import datetime

from deepeval_platform.collection.extractors.flowise_extractor import FlowiseExtractor
from deepeval_platform.collection.extractor_base import TraceExtractorBase
from deepeval_platform.collection.trace_filter import InteractionStatus
from deepeval_platform.repositories.models import TraceRecord


def _make_record(output) -> TraceRecord:
    return TraceRecord(
        trace_id="trace-1",
        session_id="sess-1",
        bot_id="my-bot",
        input={"text": "hi"},
        output=output,
        metadata={},
        start_time=datetime(2026, 1, 1, 12, 0, 0),
        end_time=None,
    )


class TestFlowiseExtractorIsSubclass:
    def test_is_trace_extractor_base_subclass(self):
        assert issubclass(FlowiseExtractor, TraceExtractorBase)


class TestFlowiseExtractorFiltering:
    def test_status_completed_returns_only_records_with_output(self):
        records = [_make_record({"text": "done"}), _make_record(None)]
        result = FlowiseExtractor().extract(records, InteractionStatus.COMPLETED)
        assert len(result) == 1
        assert result[0].output is not None

    def test_status_interrupted_returns_only_records_without_output(self):
        records = [_make_record({"text": "done"}), _make_record(None)]
        result = FlowiseExtractor().extract(records, InteractionStatus.INTERRUPTED)
        assert len(result) == 1
        assert result[0].output is None

    def test_status_none_returns_all_records(self):
        records = [_make_record({"text": "done"}), _make_record(None)]
        result = FlowiseExtractor().extract(records, None)
        assert len(result) == 2

    def test_empty_input_returns_empty_list(self):
        result = FlowiseExtractor().extract([], InteractionStatus.COMPLETED)
        assert result == []

    def test_empty_input_returns_empty_list_no_filter(self):
        result = FlowiseExtractor().extract([], None)
        assert result == []

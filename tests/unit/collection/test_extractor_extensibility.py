"""Extensibility proof for TraceExtractorBase (US3 — spec.md Acceptance Scenario 2).

Defines a throwaway TraceExtractorBase subclass for a hypothetical new bot
platform and confirms its .extract() output is indistinguishable in shape
from FlowiseExtractor/LangChainExtractor output, without touching either.
"""
from __future__ import annotations

from datetime import datetime

from deepeval_platform.collection.extractor_base import TraceExtractorBase
from deepeval_platform.collection.extractors.flowise_extractor import FlowiseExtractor
from deepeval_platform.collection.extractors.langchain_extractor import LangChainExtractor
from deepeval_platform.collection.trace_filter import InteractionStatus
from deepeval_platform.repositories.models import TraceRecord


class _ThrowawayExtractor(TraceExtractorBase):
    """Minimal extension-point extractor for a hypothetical new platform."""

    def extract(
        self,
        records: list[TraceRecord],
        status: InteractionStatus | None,
    ) -> list[TraceRecord]:
        if status is None:
            return list(records)
        if status is InteractionStatus.COMPLETED:
            return [r for r in records if r.output is not None]
        return [r for r in records if r.output is None]


def _make_record(output) -> TraceRecord:
    return TraceRecord(
        trace_id="trace-1",
        session_id=None,
        bot_id="new-platform-bot",
        input={},
        output=output,
        metadata={},
        start_time=datetime(2026, 1, 1),
        end_time=None,
    )


class TestExtractorExtensibility:
    def test_new_extractor_is_trace_extractor_base_subclass(self):
        assert issubclass(_ThrowawayExtractor, TraceExtractorBase)

    def test_new_extractor_output_shape_matches_existing_implementations(self):
        records = [_make_record({"ok": True}), _make_record(None)]

        new_result = _ThrowawayExtractor().extract(records, InteractionStatus.COMPLETED)
        flowise_result = FlowiseExtractor().extract(records, InteractionStatus.COMPLETED)
        langchain_result = LangChainExtractor().extract(records, InteractionStatus.COMPLETED)

        assert all(isinstance(r, TraceRecord) for r in new_result)
        assert new_result == flowise_result == langchain_result

    def test_existing_extractors_unaffected_by_new_extractor(self):
        """Acceptance Scenario 2: existing implementations behave unchanged."""
        records = [_make_record({"ok": True}), _make_record(None)]

        assert FlowiseExtractor().extract(records, None) == records
        assert LangChainExtractor().extract(records, None) == records

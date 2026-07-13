"""FlowiseExtractor — trace extraction strategy for Flowise-platform bots (M2.1)."""
from __future__ import annotations

from deepeval_platform.collection.extractor_base import TraceExtractorBase
from deepeval_platform.collection.trace_filter import InteractionStatus
from deepeval_platform.repositories.models import TraceRecord


class FlowiseExtractor(TraceExtractorBase):
    """Handles Flowise-platform traces.

    Flowise traces arrive via the native Langfuse integration (read-only).
    Output presence in TraceRecord.output determines completed vs. interrupted.
    """

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

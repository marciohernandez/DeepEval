"""LangChainExtractor — trace extraction strategy for LangChain/LangGraph bots (M2.1)."""
from __future__ import annotations

from deepeval_platform.collection.extractor_base import TraceExtractorBase
from deepeval_platform.collection.trace_filter import InteractionStatus
from deepeval_platform.repositories.models import TraceRecord


class LangChainExtractor(TraceExtractorBase):
    """Handles LangChain/LangGraph-platform traces.

    LangChain bots emit traces via langfuse.callback.CallbackHandler.
    Output structure may differ from Flowise (nested messages vs. plain strings),
    but completed vs. interrupted is still determined by output presence.
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

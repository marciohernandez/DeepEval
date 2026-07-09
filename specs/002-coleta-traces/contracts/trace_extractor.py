"""Contract: TraceExtractorBase ABC and platform-specific subclasses (M2.1).

This file defines the public interface surface — not runnable production code.
The real implementations live in deepeval/collection/.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from deepeval.repositories.models import TraceRecord
from specs.contracts.trace_filter import InteractionStatus  # noqa: F401 (interface reference)


class TraceExtractorBase(ABC):
    """Platform-specific trace extraction strategy (Strategy pattern).

    Encapsulates:
    - How to determine interaction completion status for this platform.
    - Any platform-specific normalization of TraceRecord fields.

    Does NOT apply sorting or the 500-interaction cap — those are
    TraceCollector responsibilities.
    """

    @abstractmethod
    def extract(
        self,
        records: list[TraceRecord],
        status: "InteractionStatus | None",
    ) -> list[TraceRecord]:
        """Filter and normalize records for this platform.

        Args:
            records: Raw TraceRecord list from TraceRepository.
            status: If provided, return only records matching this status.
                    None means return all records regardless of status.

        Returns:
            Filtered (and normalized) list of TraceRecord instances.
        """


class FlowiseExtractor(TraceExtractorBase):
    """Handles Flowise-platform traces.

    Flowise traces arrive via the native Langfuse integration (read-only).
    Output presence in TraceRecord.output determines completed vs. interrupted.
    """

    def extract(
        self,
        records: list[TraceRecord],
        status: "InteractionStatus | None",
    ) -> list[TraceRecord]: ...


class LangChainExtractor(TraceExtractorBase):
    """Handles LangChain/LangGraph-platform traces.

    LangChain bots emit traces via langfuse.callback.CallbackHandler.
    Output structure may differ from Flowise (nested messages vs. plain strings).
    """

    def extract(
        self,
        records: list[TraceRecord],
        status: "InteractionStatus | None",
    ) -> list[TraceRecord]: ...

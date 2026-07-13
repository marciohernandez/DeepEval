"""TraceExtractorBase — platform-specific trace extraction strategy (M2.1)."""
from __future__ import annotations

from abc import ABC, abstractmethod

from deepeval_platform.collection.trace_filter import InteractionStatus
from deepeval_platform.repositories.models import TraceRecord


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
        status: InteractionStatus | None,
    ) -> list[TraceRecord]:
        """Filter and normalize records for this platform.

        Args:
            records: Raw TraceRecord list from TraceRepository.
            status: If provided, return only records matching this status.
                    None means return all records regardless of status.

        Returns:
            Filtered (and normalized) list of TraceRecord instances.
        """

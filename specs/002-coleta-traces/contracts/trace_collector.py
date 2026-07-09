"""Contract: TraceCollector public interface (M2.1).

This file defines the public interface surface — not runnable production code.
The real implementation lives in deepeval/collection/trace_collector.py.
"""
from __future__ import annotations

from typing import ClassVar

from deepeval.repositories.models import TraceRecord
from deepeval.repositories.trace_repository import TraceRepository


class TraceCollector:
    """Orchestrates filtered trace collection for a single bot.

    Public contract:
    - Sole entry point for trace collection in M2.1+.
    - Delegates raw data retrieval exclusively to TraceRepository (FR-002).
    - Selects platform-specific extractor from ConfigManager, never from bot_id (FR-004).
    - Applies a hard cap of MAX_INTERACTIONS (most recent by timestamp) (FR-001).
    - Emits WARNING when cap truncates; emits DEBUG when extractor is selected (FR-012).
    - Fails fast on connectivity errors — no retry (FR-002).

    Logging behaviour:
    - DEBUG: "Selected {ExtractorClass.__name__} for bot_id={bot_id}"
    - WARNING: "Result capped at {MAX_INTERACTIONS}: {total} matches found for bot_id={bot_id}"
    """

    MAX_INTERACTIONS: ClassVar[int] = 500

    def __init__(self, repository: TraceRepository) -> None:
        """
        Args:
            repository: TraceRepository instance for raw data retrieval.
                        ConfigManager is accessed via singleton — not injected.
        """

    def collect(self, filter: "TraceFilter") -> list[TraceRecord]:  # noqa: F821
        """Collect filtered interactions for the bot specified in filter.

        Args:
            filter: A valid TraceFilter (invariants already enforced at construction).

        Returns:
            Up to MAX_INTERACTIONS TraceRecord instances, most recent first.
            Returns [] when no interactions match — never raises for empty results.

        Raises:
            TraceRepositoryError: Propagated immediately from TraceRepository on
                connectivity failure. No retry is performed.
            ConfigError: If the bot_id is not found in bots.yaml or the platform
                field is missing.
        """

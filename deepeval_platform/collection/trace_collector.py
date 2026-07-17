"""TraceCollector — orchestrates filtered trace collection for a single bot (M2.1, M4.2)."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import ClassVar

from deepeval_platform.collection.extractor_base import TraceExtractorBase
from deepeval_platform.collection.extractors.flowise_extractor import FlowiseExtractor
from deepeval_platform.collection.extractors.langchain_extractor import LangChainExtractor
from deepeval_platform.collection.trace_filter import TraceFilter
from deepeval_platform.config.config_manager import ConfigManager
from deepeval_platform.repositories.models import TraceRecord
from deepeval_platform.repositories.trace_repository import TraceRepository

logger = logging.getLogger(__name__)

_EXTRACTORS_BY_PLATFORM: dict[str, type[TraceExtractorBase]] = {
    "flowise": FlowiseExtractor,
    "langchain": LangChainExtractor,
}


class TraceCollectionSetupError(Exception):
    """Raised by collect_all() when no ID-correlatable exhaustive result can be produced
    (e.g. an empty/whitespace-only trace_id) — a whole-run failure, never a per-trace one
    (M4.2 research.md R8)."""


@dataclass
class TraceCollectionError:
    """One identified trace-specific extraction failure (M4.2 data-model.md)."""

    trace_id: str
    message: str


@dataclass
class TraceCollectionResult:
    """Exhaustive per-trace collection outcome; enforces exactly one outcome per
    non-empty trace_id across `traces`/`errors` (M4.2 data-model.md, research.md R8)."""

    traces: list[TraceRecord]
    errors: list[TraceCollectionError]

    def __post_init__(self) -> None:
        all_ids = [t.trace_id for t in self.traces] + [e.trace_id for e in self.errors]
        for trace_id in all_ids:
            if not trace_id or not trace_id.strip():
                raise ValueError(
                    "TraceCollectionResult rejects an empty/whitespace-only trace_id."
                )
        if len(all_ids) != len(set(all_ids)):
            raise ValueError(
                "TraceCollectionResult requires exactly one outcome per trace_id; "
                "duplicates must be collapsed into a single TraceCollectionError."
            )


class TraceCollector:
    """Orchestrates filtered trace collection for a single bot.

    Public contract:
    - Sole entry point for trace collection in M2.1+.
    - Delegates raw data retrieval exclusively to TraceRepository (FR-002).
    - Selects platform-specific extractor from ConfigManager, never from bot_id (FR-004).
    - Applies a hard cap of MAX_INTERACTIONS (most recent by timestamp) (FR-001).
    - Emits WARNING when cap truncates; emits DEBUG when extractor is selected (FR-012).
    - Fails fast on connectivity errors — no retry (FR-002).
    """

    MAX_INTERACTIONS: ClassVar[int] = 500

    def __init__(self, repository: TraceRepository) -> None:
        self._repository = repository

    def collect(self, filter: TraceFilter) -> list[TraceRecord]:
        platform = ConfigManager.instance().get(f"bots.{filter.bot_id}.platform")
        extractor_cls = _EXTRACTORS_BY_PLATFORM[platform]
        logger.debug(
            "Selected %s for bot_id=%s", extractor_cls.__name__, filter.bot_id
        )
        extractor = extractor_cls()

        records = self._repository.get_by_date_range(
            filter.bot_id, filter.start_date, filter.end_date
        )
        extracted = extractor.extract(records, filter.status)

        extracted.sort(key=lambda r: r.start_time or datetime.min, reverse=True)

        total = len(extracted)
        if total > self.MAX_INTERACTIONS:
            logger.warning(
                "Result capped at %d: %d matches found for bot_id=%s",
                self.MAX_INTERACTIONS, total, filter.bot_id,
            )

        return extracted[: self.MAX_INTERACTIONS]

    def collect_all(self, filter: TraceFilter) -> TraceCollectionResult:
        """Exhaustively collect every trace in [filter.start_date, filter.end_date) (M4.2 FR-004).

        Never applies MAX_INTERACTIONS. Duplicate trace IDs are collapsed into one
        TraceCollectionError with no successful record for that ID (FR-006/FR-010).
        Raises TraceCollectionSetupError for an empty/whitespace-only trace_id (no
        synthetic ID is invented) and propagates TraceRepositoryError for setup/
        connectivity failures — both are whole-run failures, never per-trace ones.
        """
        platform = ConfigManager.instance().get(f"bots.{filter.bot_id}.platform")
        extractor_cls = _EXTRACTORS_BY_PLATFORM[platform]
        logger.debug(
            "Selected %s for bot_id=%s (exhaustive)", extractor_cls.__name__, filter.bot_id
        )
        extractor = extractor_cls()

        records = self._repository.get_all_by_date_range(
            filter.bot_id, filter.start_date, filter.end_date
        )
        extracted = extractor.extract(records, filter.status)

        range_start = self._as_utc(filter.start_date)
        range_end = self._as_utc(filter.end_date)
        in_range = [
            r
            for r in extracted
            if r.start_time is not None and range_start <= self._as_utc(r.start_time) < range_end
        ]

        groups: dict[str, list[TraceRecord]] = {}
        for record in in_range:
            trace_id = record.trace_id
            if not trace_id or not trace_id.strip():
                raise TraceCollectionSetupError(
                    "collect_all() cannot invent a synthetic ID for an empty/whitespace-only "
                    "trace_id."
                )
            groups.setdefault(trace_id, []).append(record)

        traces: list[TraceRecord] = []
        errors: list[TraceCollectionError] = []
        for trace_id, group in groups.items():
            if len(group) == 1:
                traces.append(group[0])
            else:
                errors.append(
                    TraceCollectionError(
                        trace_id=trace_id,
                        message=f"{len(group)} records shared trace_id '{trace_id}'; "
                        "no canonical record could be selected.",
                    )
                )

        return TraceCollectionResult(traces=traces, errors=errors)

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        """Naive means UTC, aware is converted (same convention as EvaluationConfig, R7)."""
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

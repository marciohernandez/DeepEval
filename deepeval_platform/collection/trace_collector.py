"""TraceCollector — orchestrates filtered trace collection for a single bot (M2.1)."""
from __future__ import annotations

import logging
from datetime import datetime
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

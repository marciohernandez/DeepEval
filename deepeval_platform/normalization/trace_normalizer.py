"""TraceNormalizer — transforms one TraceRecord (M1) into one NormalizedTrace (M2.2, FR-002)."""
from __future__ import annotations

from deepeval_platform.config.config_manager import ConfigError, ConfigManager
from deepeval_platform.normalization.errors import UnmappedBotError
from deepeval_platform.normalization.field_mapper import FieldMapper
from deepeval_platform.normalization.models import NormalizedTrace
from deepeval_platform.repositories.models import TraceRecord


class TraceNormalizer:
    """Sole entry point for trace normalization in M2.2+."""

    def __init__(self, field_mapper: FieldMapper | None = None) -> None:
        self._field_mapper = field_mapper or FieldMapper()

    def normalize(self, record: TraceRecord) -> NormalizedTrace:
        """Normalize one TraceRecord into a NormalizedTrace.

        Raises:
            UnmappedBotError: record.bot_id is not in bots.yaml, or is present
                with zero declared field_mapping.* keys.
            FieldMappingTypeError: Propagated from FieldMapper when a declared,
                present path resolves to the wrong type for a list field.
        """
        bot_id = record.bot_id
        try:
            ConfigManager.instance().get(f"bots.{bot_id}.bot_type")
        except ConfigError as exc:
            raise UnmappedBotError(bot_id) from exc

        resolved_fields, declared_count = self._field_mapper.resolve_all(bot_id, record)
        if declared_count == 0:
            raise UnmappedBotError(bot_id)

        return NormalizedTrace(**resolved_fields)

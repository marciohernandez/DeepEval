"""Contract: FieldMapper public interface (M2.2).

This file defines the public interface surface — not runnable production code.
The real implementation lives in deepeval_platform/normalization/field_mapper.py.
"""
from __future__ import annotations

from typing import Any

from deepeval_platform.repositories.models import TraceRecord

# Fields whose resolved value MUST be a list; all others are unconstrained scalars.
LIST_FIELDS: frozenset[str] = frozenset({"context", "tools_called", "messages"})


class FieldMapper:
    """Resolves one bot's declared field-mapping against its raw TraceRecord.

    Public contract:
    - Reads field-mapping declarations via ConfigManager.instance() only — never
      reads bots.yaml directly (Principle V).
    - A declared path absent from one specific record resolves to that field's
      defined empty value ([] for LIST_FIELDS, None for scalar fields) — never
      raises for this case (FR-004).
    - A declared path present but resolving to the wrong type for a LIST_FIELDS
      member raises FieldMappingTypeError identifying bot_id, field, path, and
      the resolved type (FR-004).
    - For tools_called/messages, each raw list item is reshaped into the common
      per-item schema (ToolCall / Message) using the declared `<field>_item`
      sub-mapping, or same-name lookup on the item when that sub-block is
      absent (research.md Decision 4).
    - Never raises for a bot with zero declared fields — that determination
      (UnmappedBotError) is TraceNormalizer's responsibility, not FieldMapper's.
    """

    def resolve_all(
        self, bot_id: str, record: TraceRecord
    ) -> tuple[dict[str, Any], int]:
        """Resolve all seven NormalizedTrace fields for one bot's record.

        Args:
            bot_id: Bot identifier — used only to look up its field_mapping.
            record: The raw TraceRecord to resolve fields from.

        Returns:
            (resolved_fields, declared_count) where resolved_fields maps each
            of the seven NormalizedTrace field names to its resolved value
            (already defaulted/reshaped), and declared_count is how many of
            the six dot-path-mappable top-level field_mapping.* keys (all
            except metadata, which is always a full passthrough per
            research.md Decision 5) had a non-empty path declared for this
            bot (used by TraceNormalizer for FR-005).

        Raises:
            FieldMappingTypeError: A declared, present path resolved to the
                wrong type for a LIST_FIELDS member.
        """

    def resolve_field(self, bot_id: str, record: TraceRecord, field_name: str) -> Any:
        """Resolve a single NormalizedTrace field for one bot's record.

        Raises:
            FieldMappingTypeError: See resolve_all.
        """

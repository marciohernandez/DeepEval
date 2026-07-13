"""FieldMapper — resolves one bot's declared field mapping against its raw TraceRecord (M2.2)."""
from __future__ import annotations

from typing import Any

from deepeval_platform.config.config_manager import ConfigManager
from deepeval_platform.normalization.errors import FieldMappingTypeError
from deepeval_platform.normalization.models import Message, ToolCall
from deepeval_platform.repositories.models import TraceRecord

# Fields whose resolved value MUST be a list; all others are unconstrained scalars.
LIST_FIELDS: frozenset[str] = frozenset({"context", "tools_called", "messages"})

# The six dot-path-mappable NormalizedTrace fields; metadata is always a full passthrough
# (research.md Decision 5) and is never among these.
_MAPPABLE_FIELDS: tuple[str, ...] = (
    "input",
    "output",
    "context",
    "expected_output",
    "tools_called",
    "messages",
)

_ITEM_SCHEMAS: dict[str, type] = {"tools_called": ToolCall, "messages": Message}
_ITEM_SCHEMA_KEYS: dict[str, tuple[str, ...]] = {
    "tools_called": ("name", "input_parameters", "output"),
    "messages": ("role", "content"),
}

_ABSENT = object()


class FieldMapper:
    """Resolves one bot's declared field-mapping against its raw TraceRecord."""

    def resolve_all(self, bot_id: str, record: TraceRecord) -> tuple[dict[str, Any], int]:
        """Resolve all seven NormalizedTrace fields for one bot's record.

        Returns:
            (resolved_fields, declared_count) — declared_count is how many of
            the six dot-path-mappable field_mapping.* keys had a non-empty
            path declared for this bot (used by TraceNormalizer for FR-005).
        """
        resolved: dict[str, Any] = {}
        declared_count = 0
        for field_name in _MAPPABLE_FIELDS:
            path = ConfigManager.instance().get_optional(
                f"bots.{bot_id}.field_mapping.{field_name}", default=""
            )
            if path:
                declared_count += 1
            resolved[field_name] = self._resolve_declared(bot_id, field_name, record, path)
        resolved["metadata"] = record.metadata
        return resolved, declared_count

    def resolve_field(self, bot_id: str, record: TraceRecord, field_name: str) -> Any:
        """Resolve a single NormalizedTrace field for one bot's record."""
        if field_name == "metadata":
            return record.metadata
        path = ConfigManager.instance().get_optional(
            f"bots.{bot_id}.field_mapping.{field_name}", default=""
        )
        return self._resolve_declared(bot_id, field_name, record, path)

    def _resolve_declared(
        self, bot_id: str, field_name: str, record: TraceRecord, path: str
    ) -> Any:
        if not path:
            return [] if field_name in LIST_FIELDS else None

        resolved = self._resolve_path(record, path)
        if resolved is _ABSENT:
            return [] if field_name in LIST_FIELDS else None

        if field_name in LIST_FIELDS:
            if not isinstance(resolved, list):
                raise FieldMappingTypeError(bot_id, field_name, path, type(resolved))
            item_schema = _ITEM_SCHEMAS.get(field_name)
            if item_schema is not None:
                return self._reshape_list_items(bot_id, field_name, resolved, item_schema)
            return resolved

        return resolved

    def _resolve_path(self, record: TraceRecord, path: str) -> Any:
        root, *rest = path.split(".")
        if root == "input":
            current: Any = record.input
        elif root == "output":
            current = record.output
        elif root == "metadata":
            current = record.metadata
        else:
            return _ABSENT
        return self._walk(current, rest)

    @staticmethod
    def _walk(current: Any, segments: list[str]) -> Any:
        for segment in segments:
            if isinstance(current, dict):
                if segment not in current:
                    return _ABSENT
                current = current[segment]
            elif isinstance(current, list):
                try:
                    index = int(segment)
                except ValueError:
                    return _ABSENT
                try:
                    current = current[index]
                except IndexError:
                    return _ABSENT
            else:
                return _ABSENT
        return current

    def _reshape_list_items(
        self, bot_id: str, field: str, raw_list: list, item_schema: type
    ) -> list:
        reshaped = []
        for raw_item in raw_list:
            kwargs = {}
            for key in _ITEM_SCHEMA_KEYS[field]:
                item_path = ConfigManager.instance().get_optional(
                    f"bots.{bot_id}.field_mapping.{field}_item.{key}", default=""
                )
                if item_path:
                    value = self._walk(raw_item, item_path.split("."))
                elif isinstance(raw_item, dict):
                    value = raw_item.get(key, _ABSENT)
                else:
                    value = _ABSENT
                kwargs[key] = None if value is _ABSENT else value
            reshaped.append(item_schema(**kwargs))
        return reshaped

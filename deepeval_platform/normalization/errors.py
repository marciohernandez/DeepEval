"""Project-local exceptions for the normalization layer (M2.2).

Follows the ConfigError/InvalidBotTypeError convention: each message carries
every diagnostic field a caller would need without reformatting.
"""
from __future__ import annotations


class UnmappedBotError(ValueError):
    """Raised by TraceNormalizer when bot_id is unknown or has zero declared field mappings."""

    def __init__(self, bot_id: str) -> None:
        self.bot_id = bot_id
        super().__init__(
            f"No field mapping declared for bot_id '{bot_id}'. "
            f"Declare at least one field_mapping.* key under bots.{bot_id} in bots.yaml."
        )


class FieldMappingTypeError(TypeError):
    """Raised by FieldMapper when a declared, present path resolves to the wrong type."""

    def __init__(self, bot_id: str, field: str, path: str, resolved_type: type) -> None:
        self.bot_id = bot_id
        self.field = field
        self.path = path
        self.resolved_type = resolved_type
        super().__init__(
            f"Field mapping for bot_id '{bot_id}' field '{field}' (path '{path}') "
            f"resolved to type '{resolved_type.__name__}', expected list."
        )

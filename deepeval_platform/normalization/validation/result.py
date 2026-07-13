"""ValidationResult — outcome of checking a NormalizedTrace against a BotType's minimum fields."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ValidationResult:
    """Outcome of checking a NormalizedTrace against one BotType's minimum fields (FR-006, FR-007)."""

    is_valid: bool
    missing_fields: list[str] = field(default_factory=list)

"""ValidationRuleBase — abstract base for all per-BotType validation rules (M2.2, Strategy pattern)."""
from __future__ import annotations

from abc import ABC, abstractmethod

from deepeval_platform.normalization.models import NormalizedTrace
from deepeval_platform.normalization.validation.result import ValidationResult


class ValidationRuleBase(ABC):
    """Abstract base for all per-BotType validation rules (mirrors EvaluationStrategyBase).

    Extension contract (FR-008): adding a new BotType's rule requires exactly one
    new subclass + one registry entry — zero changes to existing rule subclasses,
    TraceNormalizer, or FieldMapper.
    """

    @abstractmethod
    def required_fields(self) -> list[str]:
        """Return the NormalizedTrace field names this bot type's evaluation strategy requires."""

    def validate(self, trace: NormalizedTrace) -> ValidationResult:
        """Check trace for all required_fields(); never raises (FR-006).

        A field counts as missing if it is None, or an empty list/dict/string.
        """
        missing = [
            field_name
            for field_name in self.required_fields()
            if getattr(trace, field_name) in (None, [], {}, "")
        ]
        return ValidationResult(is_valid=not missing, missing_fields=missing)

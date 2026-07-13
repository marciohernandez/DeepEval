"""Contract: ValidationRule public interface (M2.2).

This file defines the public interface surface — not runnable production code.
The real implementation lives in
deepeval_platform/normalization/validation/rule_registry.py (facade) and
deepeval_platform/normalization/validation/rule_base.py (ABC + concrete rules).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from deepeval_platform.evaluation.bot_type import BotType

NormalizedTrace = "NormalizedTrace"  # noqa: F821  (forward ref, real module imports directly)


@dataclass
class ValidationResult:
    """Outcome of checking a NormalizedTrace against one BotType's minimum fields (FR-006, FR-007)."""

    is_valid: bool
    missing_fields: list[str] = field(default_factory=list)


class ValidationRuleBase(ABC):
    """Abstract base for all per-BotType validation rules (Strategy pattern, mirrors
    EvaluationStrategyBase from M2.1).

    Extension contract (FR-008):
    - Adding a new BotType's rule requires exactly one new subclass + one
      registry entry in ValidationRule._REGISTRY.
    - Zero changes to existing rule subclasses, TraceNormalizer, or FieldMapper.
    """

    @abstractmethod
    def required_fields(self) -> list[str]:
        """Return the NormalizedTrace field names this bot type's evaluation strategy requires."""

    def validate(self, trace: "NormalizedTrace") -> ValidationResult:
        """Check trace for all required_fields(); never raises (FR-006).

        A field counts as missing if it is None, or an empty list/dict/string.

        Returns:
            ValidationResult(is_valid=True, missing_fields=[]) when all
            required fields are present and non-empty; otherwise
            ValidationResult(is_valid=False, missing_fields=[...]) naming every
            missing/empty required field (FR-007) — never a bare pass/fail.
        """


class ValidationRule:
    """Registry facade — public entry point matching FR-006's contract.

    Public contract:
    - check(trace, bot_type) accepts a NormalizedTrace and a BotType (or raw
      string coercible to BotType, matching StrategyFactory.create()'s
      convenience) and returns a ValidationResult.
    - Never raises for an invalid trace — invalidity is reported, not thrown
      (FR-006). Raises InvalidBotTypeError only for a bot_type that cannot be
      coerced to a known BotType at all (same contract as StrategyFactory).
    - Requesting a rule for a bot type that doesn't match the trace's actual
      origin is a caller error, not a validation-layer concern (spec Edge
      Cases) — ValidationRule performs no cross-check against how the trace
      was produced.
    """

    @classmethod
    def check(cls, trace: "NormalizedTrace", bot_type: BotType | str) -> ValidationResult:
        """Validate trace against bot_type's minimum-field rule.

        Raises:
            InvalidBotTypeError: bot_type cannot be coerced to a known BotType.
        """

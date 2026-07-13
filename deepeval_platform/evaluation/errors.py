"""Shared exceptions for the evaluation-orchestration layer (M3.1).

Follows the ConfigError/UnmappedBotError convention: each message carries every
diagnostic field a caller would need without reformatting. `sanitize_error()` is the
single redaction path shared by `MetricResult.error` and internal logging (research.md §6).
"""
from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

_MAX_MESSAGE_LENGTH = 500
_REDACTED = "[REDACTED]"

_BEARER_TOKEN_RE = re.compile(r"Bearer\s+\S+", re.IGNORECASE)
_OPAQUE_TOKEN_RE = re.compile(r"\b[A-Za-z0-9_\-]{20,}\b")


@dataclass
class ErrorDetail:
    category: str
    message: str


class EvaluationOrchestratorError(Exception):
    """Base class for every exception raised by EvaluationOrchestrator's pre-flight checks."""


class EmptyMetricListError(EvaluationOrchestratorError):
    """Raised when `metric_names == []` (FR-012)."""

    def __init__(self) -> None:
        super().__init__("metric_names must not be empty — at least one metric name is required.")


class UnknownMetricError(EvaluationOrchestratorError):
    """Raised when one or more requested names are not registered in MetricFactory (FR-010)."""

    def __init__(self, names: str | Iterable[str], supported: Iterable[str]) -> None:
        self.names = [names] if isinstance(names, str) else list(names)
        self.supported = sorted(supported)
        label = "Unknown metric" if len(self.names) == 1 else "Unknown metrics"
        names_str = ", ".join(f"'{n}'" for n in self.names)
        supported_str = ", ".join(f"'{n}'" for n in self.supported)
        super().__init__(f"{label} {names_str}. Supported: [{supported_str}].")


class DuplicateMetricRequestError(EvaluationOrchestratorError):
    """Raised when `metric_names` contains repeated entries (FR-010, edge case)."""

    def __init__(self, duplicates: Iterable[str]) -> None:
        self.duplicates = list(duplicates)
        duplicates_str = ", ".join(f"'{n}'" for n in self.duplicates)
        super().__init__(f"Duplicate metric name(s) requested: {duplicates_str}.")


class DuplicateMetricNameError(EvaluationOrchestratorError):
    """Raised when two MetricBase subclasses register under the same canonical name (FR-009)."""

    def __init__(self, name: str, existing_cls: type, new_cls: type) -> None:
        self.name = name
        self.existing_cls = existing_cls
        self.new_cls = new_cls
        super().__init__(
            f"Metric name '{name}' is already registered to "
            f"'{existing_cls.__name__}'; cannot register '{new_cls.__name__}' under the same name."
        )


class InvalidThresholdError(EvaluationOrchestratorError):
    """Raised when a resolved threshold is non-numeric or outside 0.0-1.0 (FR-005)."""

    def __init__(self, offending: Iterable[tuple[str, object]]) -> None:
        self.offending = list(offending)
        pairs_str = ", ".join(f"{name}={value!r}" for name, value in self.offending)
        super().__init__(
            f"Invalid threshold(s), must be numeric and within 0.0-1.0: {pairs_str}."
        )


class InvalidTimeoutError(EvaluationOrchestratorError):
    """Raised when the global default or a per-metric timeout override is non-numeric or <= 0 (FR-015)."""

    def __init__(self, offending: Iterable[tuple[str, object]]) -> None:
        self.offending = list(offending)
        pairs_str = ", ".join(f"{name}={value!r}" for name, value in self.offending)
        super().__init__(f"Invalid timeout(s), must be numeric and > 0: {pairs_str}.")


class ConfigResolutionError(EvaluationOrchestratorError):
    """Raised when ConfigManager itself raises while resolving bot config (FR-004, fail-closed)."""

    def __init__(self, bot_id: str, original: BaseException) -> None:
        self.bot_id = bot_id
        self.original = original
        super().__init__(
            f"Failed to resolve configuration for bot_id '{bot_id}': {original}"
        )
        self.__cause__ = original


def sanitize_error(exc: BaseException) -> ErrorDetail:
    """Redact API-key-shaped tokens / Bearer headers / long opaque strings and cap length."""
    category = type(exc).__name__
    message = str(exc)
    message = _BEARER_TOKEN_RE.sub(f"Bearer {_REDACTED}", message)
    message = _OPAQUE_TOKEN_RE.sub(_REDACTED, message)
    if len(message) > _MAX_MESSAGE_LENGTH:
        message = message[:_MAX_MESSAGE_LENGTH] + "...[truncated]"
    return ErrorDetail(category=category, message=message)

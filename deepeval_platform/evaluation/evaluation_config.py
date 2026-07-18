"""EvaluationConfig — passive value object for one Evaluator.start() request (M4.2).

Normalizes/validates only what needs no collaborator (UTC normalization, period
ordering). Metric/threshold/bot validation requires MetricFactory/ConfigManager and
belongs to Evaluator.start() (data-model.md, Principle I).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from deepeval_platform.evaluation.errors import InvalidPeriodError


@dataclass(frozen=True)
class MetricThreshold:
    name: str
    threshold: float


@dataclass
class EvaluationConfig:
    bot_id: str
    metric_thresholds: list[MetricThreshold]
    period_start: datetime
    period_end: datetime

    def __post_init__(self) -> None:
        self.period_start = self._to_utc(self.period_start, "period_start")
        self.period_end = self._to_utc(self.period_end, "period_end")
        if not self.period_start < self.period_end:
            raise InvalidPeriodError(self.period_start, self.period_end)

    @staticmethod
    def _to_utc(value: datetime, field_name: str) -> datetime:
        if not isinstance(value, datetime):
            raise TypeError(f"{field_name} must be a datetime, got {type(value).__name__}")
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

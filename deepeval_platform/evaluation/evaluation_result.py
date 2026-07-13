"""MetricResult + EvaluationResult — per-metric and aggregated evaluation output (M3.1, FR-006/FR-007).

EvaluationResult here is the spec's Key Entity: a distinct, in-memory, per-trace aggregate —
not `deepeval_platform.repositories.models.EvaluationResult` (M1's persisted, per-metric-row shape).
"""
from __future__ import annotations

from dataclasses import dataclass

from deepeval_platform.evaluation.errors import ErrorDetail


@dataclass
class MetricResult:
    score: float | None
    threshold: float
    passed: bool
    error: ErrorDetail | None


@dataclass
class EvaluationResult:
    passed: bool
    metrics: dict[str, MetricResult]

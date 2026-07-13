"""EvaluationContext — per-trace input passed unmodified to every MetricBase.measure() call (M3.1)."""
from __future__ import annotations

from dataclasses import dataclass

from deepeval_platform.normalization.models import NormalizedTrace


@dataclass
class EvaluationContext:
    """One instance per trace evaluation (not per metric), per FR-003."""

    trace: NormalizedTrace
    thresholds: dict[str, float]

"""ResultPublisher/ResultObserver — Observer-pattern publication contract for evaluation
results (M4.2, Constitution Principle VI). Notifies only the requester-supplied observer
for one run; concrete destination observers (Langfuse, CSV, ...) ship in their own features.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from deepeval_platform.evaluation.evaluation_result import EvaluationResult
    from deepeval_platform.evaluation.evaluation_run import EvaluationRun


class ResultObserver(ABC):
    @abstractmethod
    def publish(self, run: "EvaluationRun", results: Mapping[str, "EvaluationResult"]) -> None:
        """Receive completed results. Raise on delivery failure."""


class ResultPublisher:
    def publish(
        self,
        run: "EvaluationRun",
        results: Mapping[str, "EvaluationResult"],
        observer: ResultObserver,
    ) -> None:
        observer.publish(run, results)

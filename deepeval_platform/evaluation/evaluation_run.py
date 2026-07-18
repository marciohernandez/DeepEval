"""EvaluationRun — mutable, thread-safe run-state handle returned by Evaluator.start() (M4.2).

Every mutable backing field stays private; collaborators mutate/read state only through
public properties and behavior methods, all synchronized via a per-run RLock. No
collaborator call is ever made while that lock is held (data-model.md, Constitution
Principle I).
"""
from __future__ import annotations

import threading
import uuid
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from types import MappingProxyType
from typing import TYPE_CHECKING, Literal
from uuid import UUID

from deepeval_platform.evaluation.errors import InvalidRetryStateError, RetryInProgressError

if TYPE_CHECKING:
    from deepeval_platform.evaluation.evaluation_result import EvaluationResult
    from deepeval_platform.evaluation.result_publisher import ResultObserver


class RunStatus(str, Enum):
    STARTED = "started"
    IN_PROGRESS = "in_progress"
    DELIVERING = "delivering"
    COMPLETED = "completed"
    COMPLETED_WITH_FAILURES = "completed_with_failures"
    UNABLE_TO_RUN = "unable_to_run"
    DELIVERY_FAILED = "delivery_failed"


_TERMINAL_STATUSES = frozenset(
    {
        RunStatus.COMPLETED,
        RunStatus.COMPLETED_WITH_FAILURES,
        RunStatus.UNABLE_TO_RUN,
        RunStatus.DELIVERY_FAILED,
    }
)


class PerTraceErrorCode(str, Enum):
    EXTRACTION_FAILED = "extraction_failed"
    NORMALIZATION_FAILED = "normalization_failed"
    EVALUATION_FAILED = "evaluation_failed"


@dataclass
class PerTraceError:
    trace_id: str
    stage: Literal["extraction", "normalization", "evaluation"]
    error_code: PerTraceErrorCode
    message: str


@dataclass(frozen=True)
class EvaluationRunSnapshot:
    id: UUID
    status: RunStatus
    processed: int
    total: int | None
    progress: float | None
    start_timestamp: datetime
    end_timestamp: datetime | None
    errors: tuple[PerTraceError, ...]
    failure_message: str | None
    results: "MappingProxyType[str, EvaluationResult]" = field(default_factory=lambda: MappingProxyType({}))


class EvaluationRun:
    """UUID-keyed, mutable run-state handle. Returned immediately by Evaluator.start();
    the background worker mutates this same object in place through its public surface
    only — nothing here requires access to an underscore-prefixed field."""

    def __init__(self, observer: "ResultObserver") -> None:
        self.id: UUID = uuid.uuid4()
        self._status: RunStatus = RunStatus.STARTED
        self._processed: int = 0
        self._total: int | None = None
        self._start_timestamp: datetime = datetime.now(timezone.utc)
        self._end_timestamp: datetime | None = None
        self._errors: list[PerTraceError] = []
        self._failure_message: str | None = None
        self._results: dict[str, "EvaluationResult"] = {}
        self._observer: "ResultObserver | None" = observer
        self._state_lock = threading.RLock()
        self._retry_lock = threading.Lock()
        self._completion_event = threading.Event()

    def __repr__(self) -> str:
        return f"EvaluationRun(id={self.id!r}, status={self.status!r})"

    # ------------------------------------------------------------------
    # Read-only synchronized properties
    # ------------------------------------------------------------------
    @property
    def status(self) -> RunStatus:
        with self._state_lock:
            return self._status

    @property
    def processed(self) -> int:
        with self._state_lock:
            return self._processed

    @property
    def total(self) -> int | None:
        with self._state_lock:
            return self._total

    @property
    def start_timestamp(self) -> datetime:
        with self._state_lock:
            return self._start_timestamp

    @property
    def end_timestamp(self) -> datetime | None:
        with self._state_lock:
            return self._end_timestamp

    @property
    def errors(self) -> tuple[PerTraceError, ...]:
        with self._state_lock:
            return tuple(deepcopy(self._errors))

    @property
    def failure_message(self) -> str | None:
        with self._state_lock:
            return self._failure_message

    @property
    def results(self) -> "MappingProxyType[str, EvaluationResult]":
        with self._state_lock:
            return MappingProxyType(deepcopy(self._results))

    @property
    def progress(self) -> float | None:
        with self._state_lock:
            return self._progress_locked()

    def _progress_locked(self) -> float | None:
        if self._total is None:
            return None
        if self._total == 0:
            return 1.0
        return self._processed / self._total

    # ------------------------------------------------------------------
    # Public behavior methods — the only way collaborators mutate state
    # ------------------------------------------------------------------
    def set_total(self, total: int) -> None:
        with self._state_lock:
            self._total = total

    def increment_processed(self) -> None:
        with self._state_lock:
            self._processed += 1

    def append_error(self, error: PerTraceError) -> None:
        with self._state_lock:
            self._errors.append(error)

    def set_failure_message(self, message: str) -> None:
        with self._state_lock:
            self._failure_message = message

    def retain_results(self, results: dict[str, "EvaluationResult"]) -> None:
        with self._state_lock:
            self._results = deepcopy(results)

    def delivery_payload(self) -> tuple["MappingProxyType[str, EvaluationResult]", "ResultObserver | None"]:
        with self._state_lock:
            return MappingProxyType(deepcopy(self._results)), self._observer

    def release_observer(self) -> None:
        with self._state_lock:
            self._observer = None

    def transition_to(self, status: RunStatus) -> None:
        with self._state_lock:
            self._status = status
            self._mark_terminal_if_needed(status)

    def complete_delivery(self, status: RunStatus) -> None:
        """Atomically apply a completion status, record the first-terminal timestamp/
        signal, and release the observer — one state-lock critical section."""
        with self._state_lock:
            self._status = status
            self._mark_terminal_if_needed(status)
            self._observer = None

    def _mark_terminal_if_needed(self, status: RunStatus) -> None:
        if status in _TERMINAL_STATUSES and self._end_timestamp is None:
            self._end_timestamp = datetime.now(timezone.utc)
            self._completion_event.set()

    def snapshot(self) -> EvaluationRunSnapshot:
        with self._state_lock:
            return EvaluationRunSnapshot(
                id=self.id,
                status=self._status,
                processed=self._processed,
                total=self._total,
                progress=self._progress_locked(),
                start_timestamp=self._start_timestamp,
                end_timestamp=self._end_timestamp,
                errors=tuple(deepcopy(self._errors)),
                failure_message=self._failure_message,
                results=MappingProxyType(deepcopy(self._results)),
            )

    def wait(self, timeout: float | None = None) -> bool:
        return self._completion_event.wait(timeout)

    def begin_retry(self) -> None:
        """Atomically validate DELIVERY_FAILED and acquire the non-blocking retry guard."""
        with self._state_lock:
            if self._status != RunStatus.DELIVERY_FAILED:
                raise InvalidRetryStateError(self.id, self._status)
            if not self._retry_lock.acquire(blocking=False):
                raise RetryInProgressError(self.id)

    def end_retry(self) -> None:
        self._retry_lock.release()

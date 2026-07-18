"""Evaluator — the primary orchestration entry point for M4.2.

Validates an EvaluationConfig synchronously, then extracts/normalizes/evaluates every
trace in the requested period on a background daemon thread and delivers results to the
requester-supplied ResultObserver, returning the mutating EvaluationRun handle
immediately (research.md R1/R2). Delegates all metric scoring to the already
DeepEval-backed EvaluationOrchestrator (M3.1) — Evaluator never reimplements native
metric measurement (Constitution Principle II).
"""
from __future__ import annotations

import asyncio
import math
import threading
from typing import TYPE_CHECKING

from deepeval_platform.collection.trace_collector import TraceCollector
from deepeval_platform.collection.trace_filter import TraceFilter
from deepeval_platform.config.config_manager import ConfigError, ConfigManager
from deepeval_platform.evaluation.errors import (
    DuplicateMetricError,
    EmptyMetricListError,
    InvalidThresholdError,
    UnknownBotError,
    UnknownMetricError,
    sanitize_error,
)
from deepeval_platform.evaluation.evaluation_config import EvaluationConfig, MetricThreshold
from deepeval_platform.evaluation.evaluation_orchestrator import EvaluationOrchestrator
from deepeval_platform.evaluation.evaluation_run import (
    EvaluationRun,
    PerTraceError,
    PerTraceErrorCode,
    RunStatus,
)
from deepeval_platform.evaluation.metrics.metric_factory import MetricFactory
from deepeval_platform.evaluation.result_publisher import ResultObserver, ResultPublisher
from deepeval_platform.normalization.trace_normalizer import TraceNormalizer
from deepeval_platform.repositories.trace_repository import TraceRepository

if TYPE_CHECKING:
    from deepeval_platform.evaluation.evaluation_result import EvaluationResult


class Evaluator:
    def __init__(
        self,
        config_manager: ConfigManager | None = None,
        metric_factory: type[MetricFactory] | None = None,
        collector: TraceCollector | None = None,
        normalizer: TraceNormalizer | None = None,
        orchestrator: EvaluationOrchestrator | None = None,
        publisher: ResultPublisher | None = None,
    ) -> None:
        self._config_manager = (
            config_manager if config_manager is not None else ConfigManager.instance()
        )
        self._metric_factory = metric_factory if metric_factory is not None else MetricFactory
        self._collector = (
            collector if collector is not None else TraceCollector(TraceRepository())
        )
        self._normalizer = normalizer if normalizer is not None else TraceNormalizer()
        self._orchestrator = (
            orchestrator
            if orchestrator is not None
            else EvaluationOrchestrator(config=self._config_manager)
        )
        self._publisher = publisher if publisher is not None else ResultPublisher()

    def start(self, config: EvaluationConfig, observer: ResultObserver) -> EvaluationRun:
        thresholds = self._validate(config, observer)

        run = EvaluationRun(observer)
        try:
            thread = threading.Thread(
                target=self._run_worker, args=(run, config, thresholds), daemon=True
            )
            thread.start()
        except Exception as exc:
            run.set_failure_message(sanitize_error(exc).message)
            run.transition_to(RunStatus.UNABLE_TO_RUN)
        return run

    # ------------------------------------------------------------------
    # Pre-condition validation (FR-002/FR-014/FR-015) — all-or-nothing,
    # no EvaluationRun is ever constructed for a rejected config.
    # ------------------------------------------------------------------
    def _validate(self, config: EvaluationConfig, observer: ResultObserver) -> dict[str, float]:
        if not config.metric_thresholds:
            raise EmptyMetricListError()

        for entry in config.metric_thresholds:
            if not isinstance(entry, MetricThreshold):
                raise TypeError(
                    "metric_thresholds entries must be MetricThreshold instances, got "
                    f"{type(entry).__name__}"
                )
            if not entry.name or not entry.name.strip():
                raise ValueError("metric name must be a non-empty string")

        seen: set[str] = set()
        duplicates: list[str] = []
        for entry in config.metric_thresholds:
            if entry.name in seen and entry.name not in duplicates:
                duplicates.append(entry.name)
            seen.add(entry.name)
        if duplicates:
            raise DuplicateMetricError(duplicates)

        unknown = [
            entry.name
            for entry in config.metric_thresholds
            if not self._metric_factory.is_registered(entry.name)
        ]
        if unknown:
            raise UnknownMetricError(unknown, supported=[])

        offending: list[tuple[str, object]] = []
        for entry in config.metric_thresholds:
            value = entry.threshold
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                offending.append((entry.name, value))
                continue
            as_float = float(value)
            if not math.isfinite(as_float) or not (0.0 <= as_float <= 1.0):
                offending.append((entry.name, value))
        if offending:
            raise InvalidThresholdError(offending)

        if not config.bot_id or not config.bot_id.strip():
            raise ValueError("bot_id must be a non-empty string")

        self._validate_bot_id(config.bot_id)

        if not isinstance(observer, ResultObserver):
            raise TypeError("observer must be a non-null ResultObserver instance")

        return {entry.name: float(entry.threshold) for entry in config.metric_thresholds}

    def _validate_bot_id(self, bot_id: str) -> None:
        expected_key = f"bots.{bot_id}.bot_type"
        try:
            bot_type = self._config_manager.get(expected_key)
        except ConfigError as exc:
            if getattr(exc, "key", None) == expected_key:
                raise UnknownBotError(bot_id) from exc
            raise
        else:
            if not bot_type:
                raise UnknownBotError(bot_id)

    # ------------------------------------------------------------------
    # Background worker (US1 happy path; per-trace/whole-run failure
    # isolation is added on top of this body in Phase 5)
    # ------------------------------------------------------------------
    def _run_worker(
        self, run: EvaluationRun, config: EvaluationConfig, thresholds: dict[str, float]
    ) -> None:
        """Extract/normalize/evaluate every trace in the requested period.

        A per-trace failure (normalization or evaluation) is isolated into a
        PerTraceError and never stops the remaining traces (FR-010). Any
        non-trace-specific failure — extraction setup/connectivity, or any other
        unexpected error escaping the planned handling below — is caught by the
        outer guard and routed to a whole-run UNABLE_TO_RUN instead (FR-011).
        """
        try:
            trace_filter = TraceFilter(
                bot_id=config.bot_id, start_date=config.period_start, end_date=config.period_end
            )
            collection_result = self._collector.collect_all(trace_filter)

            total = len(collection_result.traces) + len(collection_result.errors)
            run.set_total(total)
            run.transition_to(RunStatus.IN_PROGRESS)

            metric_names = list(thresholds.keys())
            results: dict[str, "EvaluationResult"] = {}

            for collection_error in collection_result.errors:
                run.append_error(
                    PerTraceError(
                        trace_id=collection_error.trace_id,
                        stage="extraction",
                        error_code=PerTraceErrorCode.EXTRACTION_FAILED,
                        message=collection_error.message,
                    )
                )
                run.increment_processed()

            for trace in collection_result.traces:
                try:
                    normalized = self._normalizer.normalize(trace)
                except Exception as exc:
                    run.append_error(
                        PerTraceError(
                            trace_id=trace.trace_id,
                            stage="normalization",
                            error_code=PerTraceErrorCode.NORMALIZATION_FAILED,
                            message=sanitize_error(exc).message,
                        )
                    )
                    run.increment_processed()
                    continue

                try:
                    result = asyncio.run(
                        self._orchestrator.evaluate(
                            normalized, config.bot_id, metric_names, thresholds=thresholds
                        )
                    )
                except Exception as exc:
                    run.append_error(
                        PerTraceError(
                            trace_id=trace.trace_id,
                            stage="evaluation",
                            error_code=PerTraceErrorCode.EVALUATION_FAILED,
                            message=sanitize_error(exc).message,
                        )
                    )
                    run.increment_processed()
                    continue

                results[trace.trace_id] = result
                run.increment_processed()

            run.retain_results(results)
            self._deliver(run)
        except Exception as exc:
            run.set_failure_message(sanitize_error(exc).message)
            run.transition_to(RunStatus.UNABLE_TO_RUN)

    def _deliver(self, run: EvaluationRun) -> None:
        run.transition_to(RunStatus.DELIVERING)
        results_snapshot, observer = run.delivery_payload()
        try:
            self._publisher.publish(run, results_snapshot, observer)
        except Exception:
            run.transition_to(RunStatus.DELIVERY_FAILED)
        else:
            outcome = (
                RunStatus.COMPLETED if not run.errors else RunStatus.COMPLETED_WITH_FAILURES
            )
            run.complete_delivery(outcome)

    def retry_delivery(self, run: EvaluationRun) -> EvaluationRun:
        """Make exactly one new publication attempt for a DELIVERY_FAILED run, using the
        results/observer already retained on it — never re-extracts, re-normalizes, or
        re-evaluates (FR-007, SC-007). Raises InvalidRetryStateError/RetryInProgressError
        (via run.begin_retry()) without changing state if retry is not currently valid.
        """
        run.begin_retry()
        try:
            results_snapshot, observer = run.delivery_payload()
            try:
                self._publisher.publish(run, results_snapshot, observer)
            except Exception:
                pass
            else:
                outcome = (
                    RunStatus.COMPLETED if not run.errors else RunStatus.COMPLETED_WITH_FAILURES
                )
                run.complete_delivery(outcome)
        finally:
            run.end_retry()
        return run

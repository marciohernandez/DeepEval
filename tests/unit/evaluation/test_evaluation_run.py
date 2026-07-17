"""Unit tests for RunStatus/PerTraceErrorCode/PerTraceError/EvaluationRun (M4.2, data-model.md)."""
from __future__ import annotations

import threading
import time
from unittest.mock import MagicMock

import pytest

from deepeval_platform.evaluation.errors import InvalidRetryStateError, RetryInProgressError
from deepeval_platform.evaluation.evaluation_result import EvaluationResult, MetricResult
from deepeval_platform.evaluation.evaluation_run import (
    EvaluationRun,
    EvaluationRunSnapshot,
    PerTraceError,
    PerTraceErrorCode,
    RunStatus,
)


class TestRunStatus:
    def test_has_exactly_seven_values(self):
        assert {member.value for member in RunStatus} == {
            "started",
            "in_progress",
            "delivering",
            "completed",
            "completed_with_failures",
            "unable_to_run",
            "delivery_failed",
        }

    def test_is_str_enum(self):
        assert RunStatus.COMPLETED == "completed"
        assert isinstance(RunStatus.COMPLETED, str)


class TestPerTraceErrorCode:
    def test_has_exactly_three_values(self):
        assert {member.value for member in PerTraceErrorCode} == {
            "extraction_failed",
            "normalization_failed",
            "evaluation_failed",
        }


class TestPerTraceError:
    def test_holds_trace_id_stage_error_code_message(self):
        error = PerTraceError(
            trace_id="trace-1",
            stage="normalization",
            error_code=PerTraceErrorCode.NORMALIZATION_FAILED,
            message="normalization failed",
        )
        assert error.trace_id == "trace-1"
        assert error.stage == "normalization"
        assert error.error_code == PerTraceErrorCode.NORMALIZATION_FAILED
        assert error.message == "normalization failed"


@pytest.fixture
def observer():
    return MagicMock()


class TestEvaluationRunDefaults:
    def test_id_is_fresh_uuid4_per_instance(self, observer):
        run1 = EvaluationRun(observer)
        run2 = EvaluationRun(observer)
        assert run1.id != run2.id

    def test_defaults(self, observer):
        run = EvaluationRun(observer)
        assert run.status == RunStatus.STARTED
        assert run.processed == 0
        assert run.total is None
        assert run.errors == ()
        assert dict(run.results) == {}
        assert run.end_timestamp is None
        assert run.failure_message is None

    def test_progress_none_while_total_none(self, observer):
        assert EvaluationRun(observer).progress is None

    def test_progress_one_when_total_zero(self, observer):
        run = EvaluationRun(observer)
        run.set_total(0)
        assert run.progress == 1.0

    def test_progress_is_processed_over_total(self, observer):
        run = EvaluationRun(observer)
        run.set_total(4)
        run.increment_processed()
        run.increment_processed()
        assert run.progress == 0.5


class TestEvaluationRunWait:
    def test_wait_false_before_terminal(self, observer):
        assert EvaluationRun(observer).wait(0.01) is False

    def test_wait_true_after_terminal(self, observer):
        run = EvaluationRun(observer)
        run.transition_to(RunStatus.UNABLE_TO_RUN)
        assert run.wait(1.0) is True

    def test_wait_none_blocks_until_signaled(self, observer):
        run = EvaluationRun(observer)

        def complete():
            time.sleep(0.05)
            run.transition_to(RunStatus.UNABLE_TO_RUN)

        threading.Thread(target=complete).start()
        assert run.wait(None) is True

    def test_wait_non_positive_timeout_is_immediate_check(self, observer):
        run = EvaluationRun(observer)
        assert run.wait(0) is False
        assert run.wait(-1) is False

    def test_wait_invalid_type_raises_type_error(self, observer):
        with pytest.raises(TypeError):
            EvaluationRun(observer).wait("not-a-number")


class TestEvaluationRunResultsSnapshotDetachment:
    def test_results_mapping_is_read_only(self, observer):
        run = EvaluationRun(observer)
        run.retain_results({"trace-1": EvaluationResult(passed=True, metrics={})})
        with pytest.raises(TypeError):
            run.results["trace-1"] = None

    def test_results_snapshot_is_deeply_detached(self, observer):
        metric_result = MetricResult(score=0.9, threshold=0.7, passed=True, error=None)
        run = EvaluationRun(observer)
        run.retain_results(
            {"trace-1": EvaluationResult(passed=True, metrics={"faithfulness": metric_result})}
        )

        first_read = run.results
        first_read["trace-1"].metrics["faithfulness"].score = 0.1

        second_read = run.results
        assert second_read["trace-1"].metrics["faithfulness"].score == 0.9


class TestEvaluationRunTransitions:
    def test_delivering_does_not_set_end_timestamp_or_signal_wait(self, observer):
        run = EvaluationRun(observer)
        run.transition_to(RunStatus.DELIVERING)
        assert run.status == RunStatus.DELIVERING
        assert run.end_timestamp is None
        assert run.wait(0.01) is False

    def test_first_terminal_transition_sets_end_timestamp_and_signals(self, observer):
        run = EvaluationRun(observer)
        run.transition_to(RunStatus.UNABLE_TO_RUN)
        assert run.end_timestamp is not None
        assert run.wait(0.01) is True

    def test_repeated_terminal_transition_does_not_move_end_timestamp(self, observer):
        run = EvaluationRun(observer)
        run.transition_to(RunStatus.DELIVERY_FAILED)
        first_end = run.end_timestamp
        run.complete_delivery(RunStatus.COMPLETED)
        assert run.end_timestamp == first_end


class TestEvaluationRunDeliveryPayload:
    def test_returns_results_snapshot_and_retained_observer(self, observer):
        run = EvaluationRun(observer)
        run.retain_results({"trace-1": EvaluationResult(passed=True, metrics={})})
        results, obs = run.delivery_payload()
        assert dict(results) == {"trace-1": EvaluationResult(passed=True, metrics={})}
        assert obs is observer

    def test_complete_delivery_applies_status_and_releases_observer(self, observer):
        run = EvaluationRun(observer)
        run.transition_to(RunStatus.DELIVERING)
        run.complete_delivery(RunStatus.COMPLETED)
        assert run.status == RunStatus.COMPLETED
        _, obs = run.delivery_payload()
        assert obs is None

    def test_failed_delivery_retains_observer(self, observer):
        run = EvaluationRun(observer)
        run.transition_to(RunStatus.DELIVERY_FAILED)
        _, obs = run.delivery_payload()
        assert obs is observer


class TestEvaluationRunSnapshot:
    def test_returns_frozen_snapshot_with_coherent_fields(self, observer):
        run = EvaluationRun(observer)
        run.set_total(2)
        run.increment_processed()
        snap = run.snapshot()
        assert isinstance(snap, EvaluationRunSnapshot)
        assert snap.id == run.id
        assert snap.processed == 1
        assert snap.total == 2
        assert snap.progress == 0.5
        assert snap.status == RunStatus.STARTED

    def test_snapshot_fields_are_immutable(self, observer):
        snap = EvaluationRun(observer).snapshot()
        with pytest.raises(Exception):
            snap.processed = 99

    def test_snapshot_detached_errors_do_not_mutate_a_later_snapshot(self, observer):
        run = EvaluationRun(observer)
        run.append_error(
            PerTraceError(
                trace_id="t1",
                stage="evaluation",
                error_code=PerTraceErrorCode.EVALUATION_FAILED,
                message="boom",
            )
        )
        first_snapshot = run.snapshot()
        first_snapshot.errors[0].message = "mutated"

        second_snapshot = run.snapshot()
        assert second_snapshot.errors[0].message == "boom"


class TestEvaluationRunRetry:
    def test_begin_retry_requires_delivery_failed_status(self, observer):
        run = EvaluationRun(observer)
        run.transition_to(RunStatus.COMPLETED)
        with pytest.raises(InvalidRetryStateError):
            run.begin_retry()

    def test_begin_retry_succeeds_when_delivery_failed(self, observer):
        run = EvaluationRun(observer)
        run.transition_to(RunStatus.DELIVERY_FAILED)
        run.begin_retry()
        run.end_retry()

    def test_concurrent_begin_retry_raises_retry_in_progress(self, observer):
        run = EvaluationRun(observer)
        run.transition_to(RunStatus.DELIVERY_FAILED)
        run.begin_retry()
        with pytest.raises(RetryInProgressError):
            run.begin_retry()
        run.end_retry()

    def test_end_retry_releases_guard_for_next_attempt(self, observer):
        run = EvaluationRun(observer)
        run.transition_to(RunStatus.DELIVERY_FAILED)
        run.begin_retry()
        run.end_retry()
        run.begin_retry()
        run.end_retry()


class TestEvaluationRunPublicSurfaceOnly:
    def test_full_lifecycle_uses_only_public_methods(self, observer):
        run = EvaluationRun(observer)
        run.set_total(1)
        run.increment_processed()
        run.append_error(
            PerTraceError(
                trace_id="t1",
                stage="evaluation",
                error_code=PerTraceErrorCode.EVALUATION_FAILED,
                message="x",
            )
        )
        run.set_failure_message("boom")
        run.retain_results({})
        run.transition_to(RunStatus.DELIVERING)
        run.delivery_payload()
        run.complete_delivery(RunStatus.COMPLETED_WITH_FAILURES)
        run.release_observer()
        snap = run.snapshot()
        assert snap.status == RunStatus.COMPLETED_WITH_FAILURES
        assert snap.failure_message == "boom"

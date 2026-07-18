"""Unit tests for Evaluator (M4.2 US1) — validation and full-pipeline orchestration.

Stubs TraceCollector/TraceNormalizer/EvaluationOrchestrator/ResultPublisher at the
Evaluator boundary per quickstart.md — no real Langfuse/LLM call is required.
"""
from __future__ import annotations

import asyncio
import threading
import time
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from deepeval_platform.collection.trace_collector import TraceCollectionError, TraceCollectionResult
from deepeval_platform.config.config_manager import ConfigError
from deepeval_platform.evaluation.errors import (
    DuplicateMetricError,
    EmptyMetricListError,
    ErrorDetail,
    InvalidRetryStateError,
    InvalidThresholdError,
    RetryInProgressError,
    UnknownBotError,
    UnknownMetricError,
)
from deepeval_platform.evaluation.evaluation_config import EvaluationConfig, MetricThreshold
from deepeval_platform.evaluation.evaluation_result import EvaluationResult, MetricResult
from deepeval_platform.evaluation.evaluation_run import EvaluationRun, PerTraceErrorCode, RunStatus
from deepeval_platform.evaluation.evaluator import Evaluator
from deepeval_platform.evaluation.result_publisher import ResultObserver, ResultPublisher
from deepeval_platform.repositories.models import TraceRecord

_KNOWN_BOTS = {"test_rag_bot", "slow_bot", "other_bot"}


class _RecordingObserver(ResultObserver):
    def __init__(self):
        self.calls: list[tuple[object, object]] = []
        self.statuses_seen: list[RunStatus] = []

    def publish(self, run, results):
        self.statuses_seen.append(run.status)
        self.calls.append((run, results))


def _make_config(**overrides) -> EvaluationConfig:
    defaults = dict(
        bot_id="test_rag_bot",
        metric_thresholds=[MetricThreshold("faithfulness", 0.7)],
        period_start=datetime(2026, 7, 1, tzinfo=timezone.utc),
        period_end=datetime(2026, 7, 8, tzinfo=timezone.utc),
    )
    defaults.update(overrides)
    return EvaluationConfig(**defaults)


def _make_trace(trace_id: str = "trace-1", start_time: datetime | None = None) -> TraceRecord:
    return TraceRecord(
        trace_id=trace_id,
        session_id=None,
        bot_id="test_rag_bot",
        input={},
        output={"ok": True},
        metadata={},
        start_time=start_time or datetime(2026, 7, 2, tzinfo=timezone.utc),
        end_time=None,
    )


@pytest.fixture
def stub_config_manager():
    def _get(key: str) -> str:
        if key.startswith("bots.") and key.endswith(".bot_type"):
            bot_id = key[len("bots."): -len(".bot_type")]
            if bot_id in _KNOWN_BOTS:
                return "rag"
        raise ConfigError(key, "bots.yaml")

    config = MagicMock()
    config.get.side_effect = _get
    return config


@pytest.fixture
def stub_metric_factory():
    factory = MagicMock()
    factory.is_registered.side_effect = lambda name: name in {"faithfulness", "answer_relevancy"}
    return factory


@pytest.fixture
def stub_collector():
    collector = MagicMock()
    collector.collect_all.return_value = TraceCollectionResult(traces=[], errors=[])
    return collector


@pytest.fixture
def stub_normalizer():
    normalizer = MagicMock()
    normalizer.normalize.side_effect = lambda record: MagicMock(name=f"normalized-{record.trace_id}")
    return normalizer


@pytest.fixture
def stub_orchestrator():
    orchestrator = MagicMock()

    async def _evaluate(trace, bot_id, metric_names, *, thresholds=None):
        return EvaluationResult(passed=True, metrics={})

    orchestrator.evaluate = _evaluate
    return orchestrator


@pytest.fixture
def stub_publisher():
    # A real ResultPublisher so observer.publish() is actually invoked; tests that
    # need to simulate delivery failure override `.publish` on the returned instance.
    return ResultPublisher()


@pytest.fixture
def evaluator(
    stub_config_manager, stub_metric_factory, stub_collector, stub_normalizer, stub_orchestrator, stub_publisher
):
    return Evaluator(
        config_manager=stub_config_manager,
        metric_factory=stub_metric_factory,
        collector=stub_collector,
        normalizer=stub_normalizer,
        orchestrator=stub_orchestrator,
        publisher=stub_publisher,
    )


# ---------------------------------------------------------------------------
# T007 — Evaluator.start() pre-condition validation
# ---------------------------------------------------------------------------

class TestEvaluatorStartValidation:
    def test_empty_metric_thresholds_raises_and_no_run_created(self, evaluator, mocker):
        run_spy = mocker.patch("deepeval_platform.evaluation.evaluator.EvaluationRun")
        config = _make_config(metric_thresholds=[])
        with pytest.raises(EmptyMetricListError):
            evaluator.start(config, _RecordingObserver())
        run_spy.assert_not_called()

    def test_unregistered_metric_raises_unknown_metric_error(self, evaluator, mocker):
        run_spy = mocker.patch("deepeval_platform.evaluation.evaluator.EvaluationRun")
        config = _make_config(metric_thresholds=[MetricThreshold("nonexistent", 0.5)])
        with pytest.raises(UnknownMetricError):
            evaluator.start(config, _RecordingObserver())
        run_spy.assert_not_called()

    @pytest.mark.parametrize(
        "bad_threshold", [-0.1, 1.1, float("nan"), float("inf"), float("-inf"), True, "0.5"]
    )
    def test_invalid_threshold_class_raises(self, evaluator, mocker, bad_threshold):
        run_spy = mocker.patch("deepeval_platform.evaluation.evaluator.EvaluationRun")
        config = _make_config(metric_thresholds=[MetricThreshold("faithfulness", bad_threshold)])
        with pytest.raises(InvalidThresholdError):
            evaluator.start(config, _RecordingObserver())
        run_spy.assert_not_called()

    def test_arbitrary_object_threshold_raises(self, evaluator, mocker):
        run_spy = mocker.patch("deepeval_platform.evaluation.evaluator.EvaluationRun")
        config = _make_config(metric_thresholds=[MetricThreshold("faithfulness", object())])
        with pytest.raises(InvalidThresholdError):
            evaluator.start(config, _RecordingObserver())
        run_spy.assert_not_called()

    @pytest.mark.parametrize("boundary", [0, 1, 0.0, 1.0])
    def test_exact_boundary_thresholds_accepted_and_become_floats(self, evaluator, boundary):
        config = _make_config(metric_thresholds=[MetricThreshold("faithfulness", boundary)])
        run = evaluator.start(config, _RecordingObserver())
        assert isinstance(run, EvaluationRun)

    def test_duplicate_metric_name_raises(self, evaluator, mocker):
        run_spy = mocker.patch("deepeval_platform.evaluation.evaluator.EvaluationRun")
        config = _make_config(
            metric_thresholds=[
                MetricThreshold("faithfulness", 0.5),
                MetricThreshold("faithfulness", 0.6),
            ]
        )
        with pytest.raises(DuplicateMetricError):
            evaluator.start(config, _RecordingObserver())
        run_spy.assert_not_called()

    @pytest.mark.parametrize(
        "bad_entry", [{"name": "faithfulness", "threshold": 0.5}, ("faithfulness", 0.5), object()]
    )
    def test_non_metric_threshold_entry_raises_type_error(self, evaluator, mocker, bad_entry):
        run_spy = mocker.patch("deepeval_platform.evaluation.evaluator.EvaluationRun")
        config = _make_config(metric_thresholds=[bad_entry])
        with pytest.raises(TypeError):
            evaluator.start(config, _RecordingObserver())
        run_spy.assert_not_called()

    def test_unknown_bot_id_raises(self, evaluator, mocker):
        run_spy = mocker.patch("deepeval_platform.evaluation.evaluator.EvaluationRun")
        config = _make_config(bot_id="totally_unknown_bot")
        with pytest.raises(UnknownBotError):
            evaluator.start(config, _RecordingObserver())
        run_spy.assert_not_called()

    def test_config_error_for_unrelated_key_propagates_unchanged(
        self, evaluator, stub_config_manager, mocker
    ):
        stub_config_manager.get.side_effect = ConfigError("some.other.key", "settings.yaml")
        run_spy = mocker.patch("deepeval_platform.evaluation.evaluator.EvaluationRun")
        with pytest.raises(ConfigError):
            evaluator.start(_make_config(), _RecordingObserver())
        run_spy.assert_not_called()

    def test_none_observer_raises_type_error(self, evaluator, mocker):
        run_spy = mocker.patch("deepeval_platform.evaluation.evaluator.EvaluationRun")
        with pytest.raises(TypeError):
            evaluator.start(_make_config(), None)
        run_spy.assert_not_called()

    def test_non_observer_object_raises_type_error(self, evaluator, mocker):
        run_spy = mocker.patch("deepeval_platform.evaluation.evaluator.EvaluationRun")
        with pytest.raises(TypeError):
            evaluator.start(_make_config(), object())
        run_spy.assert_not_called()

    def test_empty_bot_id_raises_value_error(self, evaluator, mocker):
        run_spy = mocker.patch("deepeval_platform.evaluation.evaluator.EvaluationRun")
        config = _make_config(bot_id="   ")
        with pytest.raises(ValueError):
            evaluator.start(config, _RecordingObserver())
        run_spy.assert_not_called()

    def test_empty_metric_name_raises_value_error(self, evaluator, mocker):
        run_spy = mocker.patch("deepeval_platform.evaluation.evaluator.EvaluationRun")
        config = _make_config(metric_thresholds=[MetricThreshold("   ", 0.5)])
        with pytest.raises(ValueError):
            evaluator.start(config, _RecordingObserver())
        run_spy.assert_not_called()

    def test_mixed_validity_thresholds_all_checked_and_inputs_unchanged(self, evaluator, mocker):
        run_spy = mocker.patch("deepeval_platform.evaluation.evaluator.EvaluationRun")
        entries = [
            MetricThreshold("faithfulness", 0.5),
            MetricThreshold("answer_relevancy", -1),
        ]
        config = _make_config(metric_thresholds=entries)
        with pytest.raises(InvalidThresholdError) as exc_info:
            evaluator.start(config, _RecordingObserver())
        assert any(name == "answer_relevancy" for name, _ in exc_info.value.offending)
        run_spy.assert_not_called()
        assert entries[0].threshold == 0.5
        assert entries[1].threshold == -1


# ---------------------------------------------------------------------------
# T008 — happy-path orchestration
# ---------------------------------------------------------------------------

class TestEvaluatorHappyPath:
    def test_full_pipeline_reaches_completed(self, evaluator, stub_collector):
        traces = [_make_trace(f"trace-{i}") for i in range(3)]
        stub_collector.collect_all.return_value = TraceCollectionResult(traces=traces, errors=[])

        observer = _RecordingObserver()
        run = evaluator.start(_make_config(), observer)

        assert run.wait(5.0) is True
        assert run.status == RunStatus.COMPLETED
        assert run.processed == 3
        assert run.total == 3
        assert run.end_timestamp is not None
        assert observer.statuses_seen == [RunStatus.DELIVERING]
        assert len(observer.calls) == 1
        published_run, published_results = observer.calls[0]
        assert published_run is run
        assert set(published_results.keys()) == {t.trace_id for t in traces}


# ---------------------------------------------------------------------------
# T009 — zero-trace period
# ---------------------------------------------------------------------------

class TestEvaluatorZeroTracePeriod:
    def test_zero_traces_reaches_completed_with_one_empty_published_mapping(
        self, evaluator, stub_collector
    ):
        stub_collector.collect_all.return_value = TraceCollectionResult(traces=[], errors=[])
        observer = _RecordingObserver()

        run = evaluator.start(_make_config(), observer)

        assert run.wait(5.0) is True
        assert run.status == RunStatus.COMPLETED
        assert run.total == 0
        assert run.progress == 1.0
        assert run.errors == ()
        assert len(observer.calls) == 1
        _, results = observer.calls[0]
        assert dict(results) == {}


# ---------------------------------------------------------------------------
# T010 — independent concurrent runs
# ---------------------------------------------------------------------------

class TestEvaluatorConcurrentRuns:
    def test_two_concurrent_runs_are_independent(self, evaluator, stub_collector):
        started = threading.Event()
        release = threading.Event()

        def _collect_all(trace_filter):
            if trace_filter.bot_id == "slow_bot":
                started.set()
                release.wait(timeout=2.0)
            return TraceCollectionResult(
                traces=[_make_trace(f"trace-{trace_filter.bot_id}")], errors=[]
            )

        stub_collector.collect_all.side_effect = _collect_all

        observer_slow = _RecordingObserver()
        observer_fast = _RecordingObserver()

        run_slow = evaluator.start(_make_config(bot_id="slow_bot"), observer_slow)
        assert started.wait(timeout=2.0) is True

        run_fast = evaluator.start(_make_config(bot_id="other_bot"), observer_fast)
        assert run_fast.wait(2.0) is True
        assert run_fast.status == RunStatus.COMPLETED
        # run_slow is still blocked inside collect_all while run_fast already finished.
        assert run_slow.status in (RunStatus.STARTED, RunStatus.IN_PROGRESS)

        release.set()
        assert run_slow.wait(2.0) is True
        assert run_slow.status == RunStatus.COMPLETED

        assert run_slow.id != run_fast.id
        assert len(observer_slow.calls) == 1
        assert len(observer_fast.calls) == 1


# ---------------------------------------------------------------------------
# T047 — UTC normalization / half-open boundary reaches the collector
# ---------------------------------------------------------------------------

class TestEvaluatorPassesUtcNormalizedPeriodToCollector:
    def test_non_utc_aware_boundaries_normalized_before_reaching_collector(
        self, evaluator, stub_collector
    ):
        minus_five = timezone(timedelta(hours=-5))
        config = _make_config(
            period_start=datetime(2026, 7, 1, 7, 0, 0, tzinfo=minus_five),
            period_end=datetime(2026, 7, 8, 7, 0, 0, tzinfo=minus_five),
        )
        observer = _RecordingObserver()

        run = evaluator.start(config, observer)
        assert run.wait(5.0) is True

        stub_collector.collect_all.assert_called_once()
        (trace_filter,), _ = stub_collector.collect_all.call_args
        assert trace_filter.start_date == datetime(2026, 7, 1, 12, 0, 0, tzinfo=timezone.utc)
        assert trace_filter.end_date == datetime(2026, 7, 8, 12, 0, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# T053 — exhaustive collection beyond the M2.1 500-trace cap
# ---------------------------------------------------------------------------

class TestEvaluatorExhaustiveCollectionBeyondCap:
    def test_more_than_500_traces_all_processed_exactly_once_never_capped(
        self, evaluator, stub_collector
    ):
        traces = [_make_trace(f"trace-{i}") for i in range(600)]
        stub_collector.collect_all.return_value = TraceCollectionResult(traces=traces, errors=[])
        observer = _RecordingObserver()

        run = evaluator.start(_make_config(), observer)

        assert run.wait(5.0) is True
        assert run.status == RunStatus.COMPLETED
        assert run.total == 600
        assert run.processed == 600
        stub_collector.collect.assert_not_called()
        _, results = observer.calls[0]
        assert len(results) == 600


# ---------------------------------------------------------------------------
# T018 — immediate handle reflects pre-extraction state (US2 Scenario 1)
# ---------------------------------------------------------------------------

class TestEvaluatorImmediateHandleBeforeExtractionCompletes:
    def test_status_processed_total_before_extraction_completes(self, evaluator, stub_collector):
        release = threading.Event()

        def _collect_all(trace_filter):
            release.wait(timeout=2.0)
            return TraceCollectionResult(traces=[_make_trace()], errors=[])

        stub_collector.collect_all.side_effect = _collect_all

        observer = _RecordingObserver()
        run = evaluator.start(_make_config(), observer)

        # Extraction is still blocked — start() must have returned before it completed.
        assert run.status in (RunStatus.STARTED, RunStatus.IN_PROGRESS)
        assert run.processed == 0
        assert run.total is None

        release.set()
        assert run.wait(5.0) is True


# ---------------------------------------------------------------------------
# T019 — coherent concurrent snapshot() reads during progress (US2 Scenario 2, FR-008)
# ---------------------------------------------------------------------------

class TestEvaluatorSnapshotCoherentDuringProgress:
    def test_snapshot_coherent_and_processed_monotonic_during_progress(
        self, evaluator, stub_collector, stub_orchestrator
    ):
        traces = [_make_trace(f"trace-{i}") for i in range(5)]
        stub_collector.collect_all.return_value = TraceCollectionResult(traces=traces, errors=[])

        async def _slow_evaluate(trace, bot_id, metric_names, *, thresholds=None):
            await asyncio.sleep(0.02)
            return EvaluationResult(passed=True, metrics={})

        stub_orchestrator.evaluate = _slow_evaluate

        observer = _RecordingObserver()
        run = evaluator.start(_make_config(), observer)

        snapshots = []
        stop = threading.Event()
        violations: list[str] = []

        def _reader():
            last_processed = -1
            while not stop.is_set():
                snap = run.snapshot()
                snapshots.append(snap)
                if snap.total is not None and not (0 <= snap.processed <= snap.total):
                    violations.append(f"processed {snap.processed} out of [0, {snap.total}]")
                if snap.total is not None and snap.progress is not None:
                    expected = 1.0 if snap.total == 0 else snap.processed / snap.total
                    if snap.progress != expected:
                        violations.append(f"progress {snap.progress} != expected {expected}")
                if snap.processed < last_processed:
                    violations.append(f"processed regressed: {last_processed} -> {snap.processed}")
                last_processed = snap.processed
                time.sleep(0.001)

        reader_thread = threading.Thread(target=_reader)
        reader_thread.start()

        assert run.wait(5.0) is True
        stop.set()
        reader_thread.join(timeout=2.0)

        assert violations == []
        assert len(snapshots) > 0
        assert run.status == RunStatus.COMPLETED


# ---------------------------------------------------------------------------
# T020 — terminal timestamps set exactly once (US2 Scenario 3, FR-003/FR-009)
# ---------------------------------------------------------------------------

class TestEvaluatorTerminalTimestamps:
    def test_terminal_timestamps_set_once_and_repeated_transition_is_a_no_op(
        self, evaluator, stub_collector
    ):
        stub_collector.collect_all.return_value = TraceCollectionResult(traces=[], errors=[])
        observer = _RecordingObserver()

        run = evaluator.start(_make_config(), observer)
        assert run.wait(5.0) is True
        assert run.status == RunStatus.COMPLETED
        assert run.start_timestamp is not None
        first_end = run.end_timestamp
        assert first_end is not None

        run.transition_to(RunStatus.COMPLETED)
        assert run.end_timestamp == first_end


# ---------------------------------------------------------------------------
# T021 — observer sees DELIVERING while publish is blocked (US2 Scenario 4, FR-003/FR-007)
# ---------------------------------------------------------------------------

class TestEvaluatorObservesDeliveringWhileBlocked:
    def test_wait_false_while_publish_blocked_then_true_after_release(
        self, evaluator, stub_collector
    ):
        stub_collector.collect_all.return_value = TraceCollectionResult(
            traces=[_make_trace()], errors=[]
        )

        release = threading.Event()
        entered_publish = threading.Event()

        class _BlockingObserver(ResultObserver):
            def __init__(self):
                self.calls: list[tuple[object, object]] = []

            def publish(self, run, results):
                entered_publish.set()
                release.wait(timeout=2.0)
                self.calls.append((run, results))

        observer = _BlockingObserver()
        run = evaluator.start(_make_config(), observer)

        assert entered_publish.wait(timeout=2.0) is True
        assert run.status == RunStatus.DELIVERING
        assert run.wait(0.05) is False
        assert run.end_timestamp is None

        release.set()
        assert run.wait(2.0) is True
        assert run.status == RunStatus.COMPLETED
        assert len(observer.calls) == 1


# ---------------------------------------------------------------------------
# T024 — per-trace failure isolation (US3 Scenario 1, FR-006/FR-010)
# ---------------------------------------------------------------------------

class TestEvaluatorPerTraceFailureIsolation:
    def test_normalization_and_evaluation_failures_isolated_others_still_evaluated(
        self, evaluator, stub_collector, stub_normalizer, stub_orchestrator
    ):
        traces = [
            _make_trace("trace-norm-fail"),
            _make_trace("trace-eval-fail"),
            _make_trace("trace-ok"),
        ]
        collection_errors = [TraceCollectionError(trace_id="trace-extract-fail", message="dup")]
        stub_collector.collect_all.return_value = TraceCollectionResult(
            traces=traces, errors=collection_errors
        )

        def _normalize(record):
            if record.trace_id == "trace-norm-fail":
                raise ValueError("normalize boom Bearer sk-abcdefghij1234567890")
            return SimpleNamespace(source_trace_id=record.trace_id)

        stub_normalizer.normalize.side_effect = _normalize

        async def _evaluate(trace, bot_id, metric_names, *, thresholds=None):
            if trace.source_trace_id == "trace-eval-fail":
                raise RuntimeError("eval boom apikey=sk-proj-abcdefghijklmnopqrstuvwxyz123456")
            return EvaluationResult(passed=True, metrics={})

        stub_orchestrator.evaluate = _evaluate

        observer = _RecordingObserver()
        run = evaluator.start(_make_config(), observer)
        assert run.wait(5.0) is True

        assert run.total == 4  # 3 traces + 1 collection error
        assert run.processed == 4
        errors_by_trace = {e.trace_id: e for e in run.errors}
        assert set(errors_by_trace) == {"trace-extract-fail", "trace-norm-fail", "trace-eval-fail"}

        assert errors_by_trace["trace-extract-fail"].stage == "extraction"
        assert (
            errors_by_trace["trace-extract-fail"].error_code
            == PerTraceErrorCode.EXTRACTION_FAILED
        )

        assert errors_by_trace["trace-norm-fail"].stage == "normalization"
        assert (
            errors_by_trace["trace-norm-fail"].error_code
            == PerTraceErrorCode.NORMALIZATION_FAILED
        )
        assert "sk-abcdefghij1234567890" not in errors_by_trace["trace-norm-fail"].message

        assert errors_by_trace["trace-eval-fail"].stage == "evaluation"
        assert (
            errors_by_trace["trace-eval-fail"].error_code == PerTraceErrorCode.EVALUATION_FAILED
        )
        assert (
            "sk-proj-abcdefghijklmnopqrstuvwxyz123456"
            not in errors_by_trace["trace-eval-fail"].message
        )

        assert run.status == RunStatus.COMPLETED_WITH_FAILURES
        _, results = observer.calls[0]
        assert set(results.keys()) == {"trace-ok"}


# ---------------------------------------------------------------------------
# T025 — clean vs. failed terminal status distinguishable (US3 Scenario 2, FR-011)
# ---------------------------------------------------------------------------

class TestEvaluatorCleanVsFailedTerminalStatus:
    def test_zero_errors_reaches_completed(self, evaluator, stub_collector):
        stub_collector.collect_all.return_value = TraceCollectionResult(
            traces=[_make_trace()], errors=[]
        )
        observer = _RecordingObserver()
        run = evaluator.start(_make_config(), observer)
        assert run.wait(5.0) is True
        assert run.status == RunStatus.COMPLETED

    def test_one_or_more_errors_reaches_completed_with_failures(
        self, evaluator, stub_collector, stub_normalizer
    ):
        stub_collector.collect_all.return_value = TraceCollectionResult(
            traces=[_make_trace("bad-trace")], errors=[]
        )
        stub_normalizer.normalize.side_effect = ValueError("boom")
        observer = _RecordingObserver()
        run = evaluator.start(_make_config(), observer)
        assert run.wait(5.0) is True
        assert run.status == RunStatus.COMPLETED_WITH_FAILURES

    def test_completed_and_completed_with_failures_are_distinct_values(self):
        assert RunStatus.COMPLETED != RunStatus.COMPLETED_WITH_FAILURES


# ---------------------------------------------------------------------------
# T026 — whole-run extraction failure (Edge Cases, FR-011, research.md R5)
# ---------------------------------------------------------------------------

class TestEvaluatorWholeRunExtractionFailure:
    def test_collector_setup_failure_yields_unable_to_run(self, evaluator, stub_collector):
        stub_collector.collect_all.side_effect = RuntimeError(
            "connection failed Bearer sk-abcdefghij1234567890 "
            "password=hunter2opaquecredentialvalue1234"
        )
        observer = _RecordingObserver()
        run = evaluator.start(_make_config(), observer)

        assert run.wait(5.0) is True
        assert run.status == RunStatus.UNABLE_TO_RUN
        assert run.end_timestamp is not None
        assert run.total is None
        assert run.failure_message is not None
        assert "sk-abcdefghij1234567890" not in run.failure_message
        assert "hunter2opaquecredentialvalue1234" not in run.failure_message
        assert len(observer.calls) == 0


# ---------------------------------------------------------------------------
# T045 — unexpected worker-level failure escapes planned handling (FR-011)
# ---------------------------------------------------------------------------

class TestEvaluatorUnexpectedWorkerFailure:
    def test_unexpected_exception_outside_planned_handling_yields_unable_to_run(
        self, evaluator, stub_collector, mocker
    ):
        stub_collector.collect_all.return_value = TraceCollectionResult(traces=[], errors=[])
        mocker.patch(
            "deepeval_platform.evaluation.evaluation_run.EvaluationRun.set_total",
            side_effect=RuntimeError("unexpected bug Bearer sk-abcdefghij1234567890"),
        )
        observer = _RecordingObserver()
        run = evaluator.start(_make_config(), observer)

        assert run.wait(5.0) is True
        assert run.status == RunStatus.UNABLE_TO_RUN
        assert run.end_timestamp is not None
        assert run.failure_message is not None
        assert "sk-abcdefghij1234567890" not in run.failure_message


# ---------------------------------------------------------------------------
# T054 — metric-level vs. trace-level failure, thread-start failure (FR-006/FR-011)
# ---------------------------------------------------------------------------

class TestEvaluatorMetricLevelErrorsAndThreadStartFailure:
    def test_metric_level_error_in_result_remains_without_per_trace_error(
        self, evaluator, stub_collector, stub_orchestrator
    ):
        stub_collector.collect_all.return_value = TraceCollectionResult(
            traces=[_make_trace("trace-1")], errors=[]
        )
        metric_result = MetricResult(
            score=None,
            threshold=0.7,
            passed=False,
            error=ErrorDetail(category="TimeoutError", message="metric timed out"),
        )

        async def _evaluate(trace, bot_id, metric_names, *, thresholds=None):
            return EvaluationResult(passed=False, metrics={"faithfulness": metric_result})

        stub_orchestrator.evaluate = _evaluate

        observer = _RecordingObserver()
        run = evaluator.start(_make_config(), observer)
        assert run.wait(5.0) is True

        assert run.errors == ()
        assert run.status == RunStatus.COMPLETED
        _, results = observer.calls[0]
        assert results["trace-1"].metrics["faithfulness"].error is not None

    def test_orchestrator_exception_creates_exactly_one_evaluation_failed(
        self, evaluator, stub_collector, stub_orchestrator
    ):
        stub_collector.collect_all.return_value = TraceCollectionResult(
            traces=[_make_trace("trace-1")], errors=[]
        )

        async def _evaluate(trace, bot_id, metric_names, *, thresholds=None):
            raise RuntimeError("boom")

        stub_orchestrator.evaluate = _evaluate

        observer = _RecordingObserver()
        run = evaluator.start(_make_config(), observer)
        assert run.wait(5.0) is True

        assert len(run.errors) == 1
        assert run.errors[0].error_code == PerTraceErrorCode.EVALUATION_FAILED
        assert run.status == RunStatus.COMPLETED_WITH_FAILURES

    def test_thread_start_failure_yields_unable_to_run_not_started(self, evaluator, mocker):
        mocker.patch(
            "deepeval_platform.evaluation.evaluator.threading.Thread.start",
            side_effect=RuntimeError("can't start new thread Bearer sk-abcdefghij1234567890"),
        )
        observer = _RecordingObserver()
        run = evaluator.start(_make_config(), observer)

        assert run.status == RunStatus.UNABLE_TO_RUN
        assert run.status != RunStatus.STARTED
        assert run.wait(0.1) is True
        assert run.end_timestamp is not None
        assert run.failure_message is not None
        assert "sk-abcdefghij1234567890" not in run.failure_message


# ---------------------------------------------------------------------------
# T030 — delivery failure retains read-only, detached results (Edge Cases, FR-007, SC-006)
# ---------------------------------------------------------------------------

class TestEvaluatorDeliveryFailureRetainsResults:
    def test_publish_failure_yields_delivery_failed_with_read_only_detached_results(
        self, evaluator, stub_collector, stub_orchestrator
    ):
        stub_collector.collect_all.return_value = TraceCollectionResult(
            traces=[_make_trace("trace-1")], errors=[]
        )

        async def _evaluate(trace, bot_id, metric_names, *, thresholds=None):
            return EvaluationResult(
                passed=True,
                metrics={"faithfulness": MetricResult(score=0.9, threshold=0.7, passed=True, error=None)},
            )

        stub_orchestrator.evaluate = _evaluate

        mutation_rejected: list[bool] = []

        class _FailingObserver(ResultObserver):
            def publish(self, run, results):
                try:
                    results["trace-1"] = None
                except TypeError:
                    mutation_rejected.append(True)
                else:
                    mutation_rejected.append(False)
                results["trace-1"].metrics["faithfulness"].score = 0.0
                raise RuntimeError("delivery destination unreachable")

        observer = _FailingObserver()
        run = evaluator.start(_make_config(), observer)

        assert run.wait(5.0) is True
        assert mutation_rejected == [True]
        assert run.status == RunStatus.DELIVERY_FAILED
        assert run.end_timestamp is not None

        fresh_results = run.results
        assert fresh_results["trace-1"].metrics["faithfulness"].score == 0.9
        with pytest.raises(TypeError):
            fresh_results["trace-1"] = None


# ---------------------------------------------------------------------------
# T055 — completion + observer release is one synchronized action (FR-007, SC-004)
# ---------------------------------------------------------------------------

class TestEvaluatorCompletionReleasesObserverAtomically:
    def test_successful_initial_publication_releases_observer(self, evaluator, stub_collector):
        stub_collector.collect_all.return_value = TraceCollectionResult(
            traces=[_make_trace("trace-1")], errors=[]
        )
        observer = _RecordingObserver()
        run = evaluator.start(_make_config(), observer)

        assert run.wait(5.0) is True
        assert run.status == RunStatus.COMPLETED
        _, retained_observer = run.delivery_payload()
        assert retained_observer is None

    def test_successful_retry_releases_observer(self, evaluator, stub_collector):
        stub_collector.collect_all.return_value = TraceCollectionResult(
            traces=[_make_trace("trace-1")], errors=[]
        )
        attempts = {"count": 0}

        class _FlakyObserver(ResultObserver):
            def __init__(self):
                self.calls: list[tuple[object, object]] = []

            def publish(self, run, results):
                attempts["count"] += 1
                if attempts["count"] == 1:
                    raise RuntimeError("first attempt fails")
                self.calls.append((run, results))

        observer = _FlakyObserver()
        run = evaluator.start(_make_config(), observer)
        assert run.wait(5.0) is True
        assert run.status == RunStatus.DELIVERY_FAILED

        evaluator.retry_delivery(run)

        assert run.status == RunStatus.COMPLETED
        _, retained_observer = run.delivery_payload()
        assert retained_observer is None
        assert len(observer.calls) == 1

    def test_zero_trace_run_publishes_exactly_one_empty_detached_mapping(
        self, evaluator, stub_collector
    ):
        stub_collector.collect_all.return_value = TraceCollectionResult(traces=[], errors=[])
        observer = _RecordingObserver()
        run = evaluator.start(_make_config(), observer)

        assert run.wait(5.0) is True
        assert run.status == RunStatus.COMPLETED
        assert len(observer.calls) == 1
        _, results = observer.calls[0]
        assert dict(results) == {}


# ---------------------------------------------------------------------------
# T031 — retry_delivery() success semantics (Edge Cases, FR-007/FR-009, SC-007)
# ---------------------------------------------------------------------------

class TestEvaluatorRetryDeliverySuccess:
    def test_retry_after_publish_now_succeeds_reaches_completed_with_two_publish_calls(
        self, evaluator, stub_collector, stub_orchestrator, stub_normalizer
    ):
        stub_collector.collect_all.return_value = TraceCollectionResult(
            traces=[_make_trace("trace-1")], errors=[]
        )
        normalize_calls: list[str] = []
        evaluate_calls: list[str] = []

        def _normalize(record):
            normalize_calls.append(record.trace_id)
            return SimpleNamespace(source_trace_id=record.trace_id)

        stub_normalizer.normalize.side_effect = _normalize

        async def _evaluate(trace, bot_id, metric_names, *, thresholds=None):
            evaluate_calls.append(trace.source_trace_id)
            return EvaluationResult(passed=True, metrics={})

        stub_orchestrator.evaluate = _evaluate

        statuses_seen: list[RunStatus] = []

        class _FlakyObserver(ResultObserver):
            def publish(self, run, results):
                statuses_seen.append(run.status)
                if len(statuses_seen) == 1:
                    raise RuntimeError("first delivery fails")

        observer = _FlakyObserver()
        run = evaluator.start(_make_config(), observer)
        assert run.wait(5.0) is True
        assert run.status == RunStatus.DELIVERY_FAILED
        first_end_timestamp = run.end_timestamp

        evaluator.retry_delivery(run)

        assert run.status == RunStatus.COMPLETED
        assert run.end_timestamp == first_end_timestamp
        assert len(statuses_seen) == 2
        # Initial delivery sees DELIVERING; retry never re-enters DELIVERING and is
        # observed from the already-terminal DELIVERY_FAILED status instead.
        assert statuses_seen == [RunStatus.DELIVERING, RunStatus.DELIVERY_FAILED]
        assert normalize_calls == ["trace-1"]
        assert evaluate_calls == ["trace-1"]

    def test_retry_completed_with_failures_matches_original_trace_outcome(
        self, evaluator, stub_collector, stub_normalizer
    ):
        stub_collector.collect_all.return_value = TraceCollectionResult(
            traces=[_make_trace("bad-trace")], errors=[]
        )
        stub_normalizer.normalize.side_effect = ValueError("boom")

        attempts = {"count": 0}

        class _FlakyObserver(ResultObserver):
            def publish(self, run, results):
                attempts["count"] += 1
                if attempts["count"] == 1:
                    raise RuntimeError("first delivery fails")

        observer = _FlakyObserver()
        run = evaluator.start(_make_config(), observer)
        assert run.wait(5.0) is True
        assert run.status == RunStatus.DELIVERY_FAILED
        assert len(run.errors) == 1

        evaluator.retry_delivery(run)
        assert run.status == RunStatus.COMPLETED_WITH_FAILURES

    def test_retry_observer_receives_fresh_snapshot_unaffected_by_prior_mutation(
        self, evaluator, stub_collector, stub_orchestrator
    ):
        stub_collector.collect_all.return_value = TraceCollectionResult(
            traces=[_make_trace("trace-1")], errors=[]
        )

        async def _evaluate(trace, bot_id, metric_names, *, thresholds=None):
            return EvaluationResult(
                passed=True,
                metrics={"faithfulness": MetricResult(score=0.9, threshold=0.7, passed=True, error=None)},
            )

        stub_orchestrator.evaluate = _evaluate

        received_scores: list[float] = []

        class _MutatingThenSucceedingObserver(ResultObserver):
            def __init__(self):
                self.attempts = 0

            def publish(self, run, results):
                self.attempts += 1
                if self.attempts == 1:
                    results["trace-1"].metrics["faithfulness"].score = 0.0
                    raise RuntimeError("first delivery fails")
                received_scores.append(results["trace-1"].metrics["faithfulness"].score)

        observer = _MutatingThenSucceedingObserver()
        run = evaluator.start(_make_config(), observer)
        assert run.wait(5.0) is True

        evaluator.retry_delivery(run)
        assert received_scores == [0.9]


# ---------------------------------------------------------------------------
# T032 — retry rejected on the wrong status (Edge Cases, FR-007)
# ---------------------------------------------------------------------------

class TestEvaluatorRetryRejectedOnWrongStatus:
    @pytest.mark.parametrize(
        "status",
        [RunStatus.COMPLETED, RunStatus.IN_PROGRESS, RunStatus.DELIVERING, RunStatus.UNABLE_TO_RUN],
    )
    def test_retry_on_non_delivery_failed_status_raises_and_leaves_state_unchanged(
        self, evaluator, status
    ):
        observer = _RecordingObserver()
        run = EvaluationRun(observer)
        run.transition_to(status)
        before = run.snapshot()

        with pytest.raises(InvalidRetryStateError):
            evaluator.retry_delivery(run)

        after = run.snapshot()
        assert after.status == before.status
        assert after.processed == before.processed
        assert after.total == before.total
        assert after.start_timestamp == before.start_timestamp
        assert after.end_timestamp == before.end_timestamp
        assert after.errors == before.errors
        assert dict(after.results) == dict(before.results)
        assert after.failure_message == before.failure_message


# ---------------------------------------------------------------------------
# T033 — concurrent retry serialization (Edge Cases, FR-007)
# ---------------------------------------------------------------------------

class TestEvaluatorConcurrentRetries:
    def test_concurrent_retry_raises_retry_in_progress(self, evaluator):
        release = threading.Event()
        entered = threading.Event()

        class _BlockingObserver(ResultObserver):
            def publish(self, run, results):
                entered.set()
                release.wait(timeout=2.0)
                raise RuntimeError("still failing")

        observer = _BlockingObserver()
        run = EvaluationRun(observer)
        run.retain_results({})
        run.transition_to(RunStatus.DELIVERY_FAILED)

        thread = threading.Thread(target=evaluator.retry_delivery, args=(run,))
        thread.start()
        assert entered.wait(timeout=2.0) is True

        with pytest.raises(RetryInProgressError):
            evaluator.retry_delivery(run)

        release.set()
        thread.join(timeout=2.0)
        assert run.status == RunStatus.DELIVERY_FAILED

    def test_retry_after_failed_attempt_can_retry_again(self, evaluator):
        attempts = {"count": 0}

        class _FlakyObserver(ResultObserver):
            def publish(self, run, results):
                attempts["count"] += 1
                if attempts["count"] < 2:
                    raise RuntimeError("still failing")

        observer = _FlakyObserver()
        run = EvaluationRun(observer)
        run.retain_results({})
        run.transition_to(RunStatus.DELIVERY_FAILED)

        evaluator.retry_delivery(run)
        assert run.status == RunStatus.DELIVERY_FAILED

        evaluator.retry_delivery(run)
        assert run.status == RunStatus.COMPLETED

    def test_retry_after_successful_transition_raises_invalid_state_and_makes_no_new_publish(
        self, evaluator
    ):
        publish_calls: list[int] = []

        class _SucceedingObserver(ResultObserver):
            def publish(self, run, results):
                publish_calls.append(1)

        observer = _SucceedingObserver()
        run = EvaluationRun(observer)
        run.retain_results({})
        run.transition_to(RunStatus.DELIVERY_FAILED)

        evaluator.retry_delivery(run)
        assert run.status == RunStatus.COMPLETED
        assert len(publish_calls) == 1

        with pytest.raises(InvalidRetryStateError):
            evaluator.retry_delivery(run)
        assert len(publish_calls) == 1

"""Unit tests for Evaluator (M4.2 US1) — validation and full-pipeline orchestration.

Stubs TraceCollector/TraceNormalizer/EvaluationOrchestrator/ResultPublisher at the
Evaluator boundary per quickstart.md — no real Langfuse/LLM call is required.
"""
from __future__ import annotations

import threading
import time
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from deepeval_platform.collection.trace_collector import TraceCollectionResult
from deepeval_platform.config.config_manager import ConfigError
from deepeval_platform.evaluation.errors import (
    DuplicateMetricError,
    EmptyMetricListError,
    InvalidThresholdError,
    UnknownBotError,
    UnknownMetricError,
)
from deepeval_platform.evaluation.evaluation_config import EvaluationConfig, MetricThreshold
from deepeval_platform.evaluation.evaluation_result import EvaluationResult
from deepeval_platform.evaluation.evaluation_run import EvaluationRun, RunStatus
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

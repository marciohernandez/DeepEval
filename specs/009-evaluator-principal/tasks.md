---

description: "Task list for M4.2 Evaluator Principal"
---

# Tasks: Evaluator Principal

**Input**: Design documents from `/specs/009-evaluator-principal/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/evaluator-api.md, quickstart.md

**Tests**: Mandatory per Constitution Principle IV (strict TDD). Every production task is preceded
by a test task that must be written and observed RED before the corresponding implementation is
written GREEN.

**Organization**: Tasks are grouped by user story (US1/US2/US3 from spec.md) to enable independent
implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: Maps task to US1/US2/US3
- File paths are exact, per plan.md's Project Structure section

## Path Conventions

Single project (existing `deepeval_platform/` package):
- Source: `deepeval_platform/evaluation/`
- Unit tests: `tests/unit/evaluation/`
- Collection/repository changes: `deepeval_platform/collection/`,
  `deepeval_platform/repositories/`, `tests/unit/collection/`, and `tests/unit/repositories/`
- Integration tests: `tests/integration/`

---

## Phase 1: Setup

**Purpose**: No new project scaffolding is required — `deepeval_platform/evaluation/` and
`tests/unit/evaluation/`/`tests/integration/` already exist (M3.1/M4.1). This phase only confirms
the ground is ready.

- [ ] T001 Confirm `uv run pytest tests/unit/evaluation/test_evaluation_orchestrator.py -v` passes
       on the current branch before any new code is added (establishes the relevant pre-change
       baseline); T040 verifies the coverage gate after feature implementation

**Checkpoint**: Baseline green; safe to add new files.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: New exception classes and the public metric-registration query that every user story's
validation and retry paths depend on. No test/implementation in Phase 3+ can reference these until
they exist.

**⚠️ CRITICAL**: Must complete before any user story work begins.

- [ ] T002 [P] Add failing unit tests for `UnknownBotError`, `InvalidPeriodError`,
      `InvalidRetryStateError`, `RetryInProgressError`, and `DuplicateMetricError` (message/attribute shape, per research.md R4
      and data-model.md) in `tests/unit/evaluation/test_errors.py` — run and observe RED
- [ ] T003 Add `UnknownBotError`, `InvalidPeriodError`, `InvalidRetryStateError`,
      `RetryInProgressError`, and `DuplicateMetricError` to `deepeval_platform/evaluation/errors.py`, following the file's
      existing `EvaluationOrchestratorError` subclass convention (each carries every diagnostic
      field a caller needs, per research.md R4/R6) — GREEN for T002 (depends on T002)
- [ ] T049 [P] Add failing unit tests for the public `MetricFactory.is_registered(name)` query in
      `tests/unit/evaluation/metrics/test_metric_factory.py`: registered names return `True`, unknown names
      return `False`, and callers do not need access to `_registry` — run and observe RED
- [ ] T050 Implement `MetricFactory.is_registered(name)` in
      `deepeval_platform/evaluation/metrics/metric_factory.py` as the public registry-membership
      query — GREEN for T049 (depends on T049)

**Checkpoint**: Foundational error types and the encapsulated metric-registration query exist; user
story implementation can begin.

---

## Phase 3: User Story 1 - Trigger a full evaluation run for a bot (Priority: P1) 🎯 MVP

**Goal**: A caller supplies `bot_id`, metrics/thresholds, a period, and one `ResultObserver`;
`Evaluator.start()`
validates the config, extracts/normalizes/evaluates every trace in the period, and delivers
       results through `ResultPublisher`, reaching `COMPLETED` (or `COMPLETED_WITH_FAILURES` if a trace
failed — covered fully in US3, but the terminal-status distinction must exist by the end of this
phase since `RunStatus` is defined here).

**Independent Test**: Start a run for a bot with known stub traces in a known period (via stubbed
       `TraceCollector`/`TraceNormalizer`/`EvaluationOrchestrator`/`ResultPublisher`) and confirm the run
       reaches `COMPLETED` with one `EvaluationResult` per trace recorded by the stub publisher — no US2/US3
capability required.

### Tests for User Story 1 ⚠️

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [ ] T004 [P] [US1] Add failing unit tests for the public `EvaluationConfig` contract in
       `tests/unit/evaluation/test_evaluation_config.py`: UTC normalization of naive/aware
       `period_start`/`period_end` (research.md R7), `InvalidPeriodError` when `period_end` is not
       strictly later than `period_start` (raised in `__post_init__`, no collaborator needed), and
       preservation of duplicate metric-threshold entries until `Evaluator.start()` validates
       them. Define minimal test-local placeholder types only when needed to keep this test module
       importable before production types exist; replace those placeholders with production imports
       only after observing RED. Also test that constructing a `MetricThreshold` without either
       `name` or `threshold` is rejected before an `EvaluationConfig` can be submitted, while supplied
       raw threshold values are not silently coerced by construction. Assert naive datetimes mean
       UTC, aware datetimes are converted, and non-datetime boundaries raise `TypeError` — run and
       observe RED
- [ ] T005 [P] [US1] Add failing unit tests for `RunStatus`/`PerTraceErrorCode`/`PerTraceError` in
       `tests/unit/evaluation/test_evaluation_run.py`: `RunStatus` has exactly the seven values from
       data-model.md; `PerTraceErrorCode` has exactly `extraction_failed`, `normalization_failed`,
       and `evaluation_failed`; `PerTraceError` holds `trace_id`/`stage`/`error_code`/`message`.
       Keep this test independently executable before `EvaluationRun` exists — run and observe RED
- [ ] T006 [US1] After T013 makes the prerequisite enums/value objects importable, add failing unit tests for `EvaluationRun` in
        `tests/unit/evaluation/test_evaluation_run.py`: `id` is a fresh `uuid4()` per instance,
        `processed`/`total`/`errors` default correctly, `progress` is `None` while `total is None`,
         `1.0` when `total == 0`, else `processed / total`; `wait(timeout)` returns `False` before a
          terminal state and `True` after one, with `None`/non-positive/invalid timeout behavior
          matching `threading.Event.wait()`; `results` starts empty and returns a read-only snapshot
         that does not allow mapping mutation and is deeply detached so mutating a nested
         `MetricResult` does not alter a later `run.results` snapshot; public run-state, delivery,
          transition, and retry methods preserve their invariants, including that transition to
          non-terminal `DELIVERING` leaves `end_timestamp` unset and `wait()` unsignaled, without
          requiring access to any underscore-prefixed field. Assert `snapshot()` returns a frozen
          `EvaluationRunSnapshot` whose status/counts/progress/timestamps/errors/results come from
          one locked state, and that detached errors/results cannot mutate later snapshots. Assert
           `delivery_payload()` returns exactly `(fresh_results_snapshot, retained_observer)` and
            successful delivery atomically reaches its completion status and releases the private
            observer through a public behavior method while
           failed delivery retains it. Assert retry status validation plus guard acquisition is atomic (FR-003, FR-007, FR-008,
          Constitution Principle I) — run and observe RED (depends on T005
       existing in the same file)
- [ ] T007 [US1] After T012/T014/T034/T050 make the public collaborator and model contracts
        importable, add failing unit tests for `Evaluator.start()` pre-condition validation in
        `tests/unit/evaluation/test_evaluator.py`: empty `metric_thresholds` → `EmptyMetricListError`,
        unregistered metric → `UnknownMetricError`; each invalid threshold class (below zero, above
       one, `NaN`, either infinity, boolean, numeric string, and arbitrary object) →
       `InvalidThresholdError`; exact integer/float boundaries `0` and `1` are accepted and become
       floats only in the validated internal mapping;
          duplicate metric name → `DuplicateMetricError`; mappings, tuples, and arbitrary look-alike
          entries → `TypeError`; an explicit missing-key outcome or empty result from lookup of the
          exact `bots.{bot_id}.bot_type` key → `UnknownBotError`; configuration parsing/loading and
          other `ConfigError` failures propagate unchanged — assert no `EvaluationRun` is ever constructed for any
       of these; `None` or an object that is not a `ResultObserver` → `TypeError` with no run
        constructed (use a stubbed `ConfigManager`/`MetricFactory`). Include empty and whitespace-only
        bot IDs and metric names. Add a mixed-validity entry list proving all submitted entries are
        validated before float conversion or internal mapping construction and that caller inputs
        remain unchanged — run and observe RED (depends on T012, T014, T034, T050)
- [ ] T008 [US1] Add failing unit tests for `Evaluator.start()` happy-path orchestration in
       `tests/unit/evaluation/test_evaluator.py`: stubbed `TraceCollector.collect_all()` returns a
       `TraceCollectionResult` containing N uniquely identified traces, stubbed
        `TraceNormalizer`/`EvaluationOrchestrator` succeed for each, a requester-supplied observer
       receives only its run's `(run, results)` through `ResultPublisher.publish`, observes
       `run.status == DELIVERING` inside that callback, and delivery succeeds →
       `run.status == COMPLETED`, `run.processed == N`,
      `run.total == N`, `run.end_timestamp` set once — run and observe RED (depends on T007 in the
      same file)
- [ ] T009 [US1] Add failing unit test for zero-trace period in
      `tests/unit/evaluation/test_evaluator.py`: stubbed `TraceCollector.collect_all()` returns an
      empty `TraceCollectionResult` →
       `run.total == 0`, `run.progress == 1.0`, one empty detached mapping published to the supplied
       observer, `run.status == COMPLETED`, no error recorded (US1
      Scenario 2, SC-004) — run and observe RED
- [ ] T010 [US1] Add failing unit test for independent concurrent runs in
       `tests/unit/evaluation/test_evaluator.py`: two `start()` calls, including the same bot with
       overlapping periods, via a
       slow stub collector and separate requester observers yield distinct `run.id`s with
       independently correct terminal state and overlapping thread lifetimes; each observer
        receives only its own run's results. While one run is blocked in delivery/retry, repeatedly
        mutate/read the other and prove per-run locks do not serialize unrelated runs (US1 Scenario
        3, FR-007, FR-012) — run and observe RED
- [ ] T011 [P] [US1] Add failing unit tests for `EvaluationOrchestrator.evaluate()`'s new optional
       `thresholds` keyword parameter in `tests/unit/evaluation/test_evaluation_orchestrator.py`:
       when provided, scoring uses the override instead of the `bots.yaml`-resolved threshold; when
       omitted, existing config-lookup behavior is unchanged (research.md R3, FR-013) — run and
       observe RED
- [ ] T047 [US1] Add a failing unit test in `tests/unit/evaluation/test_evaluator.py`: start a run
       with non-UTC aware period boundaries and assert the stubbed `TraceCollector.collect_all()` receives the
       equivalent UTC-normalized start/end values, treating the requested interval as `[start, end)`
       so a start-boundary trace is included and an end-boundary trace is excluded — run and observe
       RED (FR-004; depends on T008's evaluator test scaffolding)
- [ ] T053 [US1] Add a failing unit test in `tests/unit/evaluation/test_evaluator.py`: provide a
       stubbed `TraceCollector.collect_all()` result containing more than 500 traces, assert the
       Evaluator never calls capped `collect()`, and confirm every trace is processed exactly once
       and produces one result (FR-004, SC-001/SC-002) — run and observe RED (depends on T008's
       evaluator test scaffolding)
- [ ] T037 [US1] Add `tests/integration/test_evaluator_flow_integration.py` (marked `-m integration`)
       using an in-process HTTP server that serves deterministic paginated responses with the
       Langfuse `{data, meta}` contract. Exercise real `TraceRepository` →
       `TraceCollector.collect_all()` → `TraceNormalizer` → `EvaluationOrchestrator` →
       `ResultPublisher` → observer composition for a directly populated test `ConfigManager`;
       replace only the external judge-model boundary with a deterministic `DeepEvalBaseLLM` fake.
       Assert all response pages are consumed, the run reaches `COMPLETED`, and the observer
       receives one `EvaluationResult` per fixture trace. The file MUST NOT read `.env`, access an
       external host, call `pytest.skip`, or use `skip`/`skipif` markers. Observe RED before
        production implementation begins. This task MUST complete and be observed RED before T015,
        T016, T017, T035, T044, or T052 begins (depends on T004, T006, T007, T008, T042, T043,
        T049, T051 test contracts being present)

### Implementation for User Story 1

- [ ] T012 [P] [US1] Implement frozen `MetricThreshold(name: str, threshold: float)` and the
       `EvaluationConfig` dataclass in `deepeval_platform/evaluation/evaluation_config.py`:
       `bot_id: str`, `metric_thresholds: list[MetricThreshold]`, `period_start`/`period_end:
       datetime`, with `__post_init__` UTC normalization and eager `InvalidPeriodError` check.
       Preserve the submitted list unchanged so duplicate names remain detectable by
       `Evaluator.start()` (data-model.md, research.md R1/R7) — GREEN for T004 (depends on T003
       for `InvalidPeriodError`; depends on T004 having been executed and observed RED)
- [ ] T013 [P] [US1] Implement `RunStatus(str, Enum)`, `PerTraceErrorCode(str, Enum)`, and
       `PerTraceError` dataclass in `deepeval_platform/evaluation/evaluation_run.py`
       (data-model.md) — GREEN for T005 (depends on T003 and T005 having been executed and observed RED)
- [ ] T014 [US1] Implement `EvaluationRun` dataclass in
        `deepeval_platform/evaluation/evaluation_run.py`: private backing fields for mutable status,
         counts, timestamps, errors, failure message, results, and observer; private
         `_state_lock: threading.RLock`, `_retry_lock`, and `_completion_event` (excluded from
         `repr`/equality); synchronized read-only public properties for state,
         a public `results` property returning a read-only snapshot, derived `progress` property, and
         `wait(timeout)` backed by the event. Add public behavior methods `set_total`,
         `increment_processed`, `append_error`, `set_failure_message`, `retain_results`,
           `delivery_payload`, `release_observer`, `transition_to`, `complete_delivery`, `snapshot`, `begin_retry`, and
          `end_retry`; these methods own
         the private backing state, first-terminal timestamp/event signaling, and retry-lock
          invariants so collaborators never access underscore-prefixed fields directly.
          `complete_delivery()` MUST set the successful final status and clear the observer in one
          state-lock critical section
         (data-model.md, Constitution Principle I). Implement `retain_results()` with `deepcopy`
         into canonical storage; implement `results` and `delivery_payload()` with a fresh
         `MappingProxyType(deepcopy(...))` on every call. Implement frozen
         `EvaluationRunSnapshot` and ensure no collaborator call occurs while `_state_lock` is held
         — GREEN for T006
         (depends on T006 having been executed and observed RED after T013)
- [ ] T043 [P] [US1] Add failing unit tests in `tests/unit/collection/test_trace_collector.py` for
       additive `collect_all()`: more than 500 traces are returned without truncation, UTC
       half-open boundaries are rechecked locally, identified per-trace extraction failures are
       returned alongside successful traces, and setup/connectivity failure before a trace is
       identified still raises. Return duplicate IDs across records and mixed success/error
        outcomes, including errors-only duplicates and duplicates split across repository pages;
        assert each duplicated ID becomes exactly one sanitized `TraceCollectionError`,
       no successful record with that ID remains, unique traces are unaffected, and total outcomes
       equal unique IDs. Assert directly constructing an invalid `TraceCollectionResult` with
        repeated IDs is rejected. Assert empty and whitespace-only IDs invalidate collection rather
        than receiving synthetic IDs. Add a regression assertion that existing `collect()` remains
       capped at the most recent 500 — run and observe RED
- [ ] T051 [P] [US1] Add failing unit tests in
       `tests/unit/repositories/test_trace_repository.py` for `get_all_by_date_range()`: mock
       Langfuse `{data, meta}` responses across multiple `page` values, assert every row is returned
         exactly once through `meta.totalPages` using one implementation-owned fixed page size and
         ascending trace timestamp plus trace-ID tie-break ordering on every request. Include equal
         timestamps and reject records missing either ordering component as malformed, and
        assert missing or malformed pagination metadata
        raises `TraceRepositoryError` rather than returning a partial result. Also cover repeated
        page numbers/data, `totalPages` changing between responses, and an empty page before the
        declared final page; each inconsistency must terminate with `TraceRepositoryError`, never
        loop or silently omit data — run and observe RED
- [ ] T052 [US1] Implement additive `TraceRepository.get_all_by_date_range()` in
       `deepeval_platform/repositories/trace_repository.py`: request `GET /api/public/traces` with
         `page`/fixed `limit` plus bot/date filters and ascending trace timestamp/trace-ID ordering,
         append each page's data through a stable
        `meta.totalPages`, rejecting repeated/changing/malformed pagination or premature empty pages, and
        preserve the existing repository methods unchanged — GREEN for T051 (depends on T037 and
        T051 having been executed and observed RED)
- [ ] T044 [US1] Implement additive `TraceCollector.collect_all()` in
       `deepeval_platform/collection/trace_collector.py` to call
       `TraceRepository.get_all_by_date_range()`, return `TraceCollectionResult` with every
       successful trace and identified `TraceCollectionError`, enforce `[start, end)` locally, and
       never apply `MAX_INTERACTIONS`. Before constructing `TraceCollectionResult`, group all
        outcomes by non-empty `trace_id`; reject an empty/whitespace-only ID as an invalid exhaustive
        result; replace every duplicate-ID group with one sanitized
       extraction error and no successful record. Enforce the same one-outcome-per-ID invariant in
        `TraceCollectionResult` construction. Preserve capped `collect()` unchanged — GREEN for T043
        (depends on T037, T043 having been executed and observed RED, and T052)
- [ ] T042 [P] [US1] Add failing unit tests for `ResultPublisher`/`ResultObserver` in
          `tests/unit/evaluation/test_result_publisher.py`: define `ResultObserver` as an ABC with
          abstract `publish(run, results: Mapping)`; assert it cannot be instantiated directly,
          concrete subclasses satisfy runtime `isinstance`, and
          `ResultPublisher.publish(run, results, observer)` invokes only the supplied observer and
          propagates that observer's errors to the caller — run and
        observe RED
- [ ] T034 [US1] Implement `ResultPublisher` and `ResultObserver` in
          `deepeval_platform/evaluation/result_publisher.py`: implement `ResultObserver` as the ABC
          contract defined by T042; the publisher notifies only the supplied
         observer through `publish(run, results: Mapping[str, EvaluationResult], observer)` and
         propagates observer errors to
        `Evaluator` —
       GREEN for T042 (depends on T042 having been executed and observed RED; use forward/type-only
       references so this interface does not require T014)
- [ ] T015 [US1] Add the optional keyword-only `thresholds: dict[str, float] | None = None`
      parameter to `EvaluationOrchestrator.evaluate()` in
      `deepeval_platform/evaluation/evaluation_orchestrator.py`, routing `_resolve_thresholds` to
      use it directly when provided instead of reading `bots.yaml` (research.md R3) — GREEN for
       T011 (depends on T011 and T037 having been executed and observed RED)
- [ ] T016 [US1] Implement `Evaluator.__init__` and `Evaluator.start()` pre-condition validation in
        `deepeval_platform/evaluation/evaluator.py`: accept optional injectable `config_manager`,
        `metric_factory`, `collector`, `normalizer`, `orchestrator`, and `publisher` collaborators;
        compose production defaults only for omitted collaborators, passing the selected config
        manager to the default `EvaluationOrchestrator` and constructing the default collector with
        `TraceRepository`. Validate the submitted `metric_thresholds`
       entry list is non-empty, every entry is an actual `MetricThreshold`, every entry name is
       unique, every name is known through the public
       `MetricFactory.is_registered(name)` query,
       and every entry threshold is an `int`/`float` excluding `bool`, finite according to
       `math.isfinite(float(value))`, and in `[0.0, 1.0]`. Do not coerce strings. Only after every
       entry passes all checks, build the internal `dict[str, float]` threshold mapping with
       normalized float values. Validate `bot_id` via
         the selected config manager's `get(f"bots.{bot_id}.bot_type")`, translating only its
          explicit missing-key outcome or empty returned value to `UnknownBotError` and allowing
          parsing/loading and other `ConfigError` failures to propagate; validate that `observer` is a non-null `ResultObserver` and raise
          `TypeError` before creating a run otherwise (research.md R1/R4) — GREEN for T007 (depends
          on T007 and T037 having been executed and observed RED, plus T012, T014, T003, T034, T050)
- [ ] T017 [US1] Implement `Evaluator.start()`'s run creation and background-thread orchestration in
        `deepeval_platform/evaluation/evaluator.py`: on successful validation, construct
         `EvaluationRun` with the requester-supplied observer accepted as a constructor argument and
          retained in private backing state, then spawn a daemon
          `threading.Thread` whose worker calls `TraceCollector.collect_all()` and never capped `collect()`,
       then per trace calls `TraceNormalizer.normalize()` and
       `asyncio.run(EvaluationOrchestrator.evaluate(..., thresholds=validated_thresholds))`,
          accumulating `results` and retaining them on the run for T035's initial publication;
         use public progress/error methods for all state updates. If thread creation/start fails
          after run creation, sanitize the failure, transition that run to `UNABLE_TO_RUN`, and
          return that accepted terminal handle rather than propagating the startup exception.
          Delegate all metric scoring to the existing DeepEval-backed
         `EvaluationOrchestrator`; do not reproduce native metric measurement logic in `Evaluator`;
         treat a returned `EvaluationResult`, including supported metric-level errors, as a trace
         result and create `evaluation_failed` only when the orchestrator raises; return the run
          immediately (research.md R2/R8) — provides the extraction/normalization/evaluation and
           retention portion required by T008, T009, T010, T047, and T053 (depends on those tests
          and T037 having been executed and observed RED, plus T016, T015, T034, T044)

- [ ] T035 [US1] Implement initial result delivery in `Evaluator.start()`'s background-thread body
         (`deepeval_platform/evaluation/evaluator.py`): call `run.retain_results(results)` after trace
        processing, transition to non-final `DELIVERING`, unpack
        `results_snapshot, observer = run.delivery_payload()`, and call
        `self._publisher.publish(run, results_snapshot, observer)`. On exception transition to
        `DELIVERY_FAILED` while retaining observer and results; on success call the synchronized
        `run.complete_delivery(outcome)` operation that both applies the selected completion status
        and releases the observer. Every payload, including the zero-trace mapping, is a fresh
        detached read-only snapshot — GREEN for T008, T009 and T021 (depends on T017 and T028;
        complete this task after Phase 5's T028, before the Phase 3 checkpoint is declared met)

**Deferred Checkpoint**: The Phase 3 implementation is structurally complete here, but User Story 1
is declared fully functional only after T028 selects the terminal outcome and T035 is completed and
rerun; then a full run reaches a terminal status through the real pipeline composition with stubbed
collaborators.

---

## Phase 4: User Story 2 - Observe the status of an in-progress run (Priority: P2)

**Goal**: While a run executes, its already-returned `EvaluationRun` handle reflects live
`status`/`processed`/`total`/`progress`/timestamps without any separate polling API.

**Independent Test**: Start a run and, before it finishes, read the same handle's `status` and
`processed`/`total` to confirm they reflect an in-progress state and increase as traces are
processed, using only the US1 `Evaluator`/`EvaluationRun` machinery already built.

### Tests for User Story 2 ⚠️

- [ ] T018 [US2] Add failing unit test in `tests/unit/evaluation/test_evaluator.py`: immediately
      after `start()` returns (before the background thread has progressed), `run.status` is
      `STARTED` (or already `IN_PROGRESS`), `run.processed == 0`, and `run.total is None` if
      extraction has not yet completed (US2 Scenario 1) — run and observe RED
- [ ] T019 [US2] Add failing unit test in `tests/unit/evaluation/test_evaluator.py`, using a
       stub collector/orchestrator with an artificial delay per trace: while the run is partway
       through, repeatedly call `run.snapshot()` from a concurrent reader and assert each snapshot
       has a coherent status/count/progress combination (`0 <= processed <= total` once total is
       known, progress derived from those same counts), with monotonic processed counts and no
       partially-applied transition (US2 Scenario 2, FR-008) — run and observe RED
- [ ] T020 [US2] Add failing unit test in `tests/unit/evaluation/test_evaluator.py`: once a run
       reaches its first terminal status via `run.wait(timeout)`, `run.start_timestamp` and
       `run.end_timestamp` are both set, and repeated `run.transition_to()` calls do not
       change `run.end_timestamp` (US2 Scenario 3, FR-003, FR-009, data-model.md's end-timestamp
       rule) — run and observe RED
- [ ] T021 [US2] Add failing unit test in `tests/unit/evaluation/test_evaluator.py` asserting
       `start()` returns before the stubbed pipeline's delivery call has been reached and
       the observer sees `run.status == DELIVERING` while delivery is blocked;
       `run.wait(short_timeout)` returns `False` and `run.end_timestamp is None` during that state,
       then the wait returns `True` after delivery is released, without any second call to
       `Evaluator` (US2 Scenario 4, FR-003, FR-007) — run and observe RED

### Implementation for User Story 2

- [ ] T022 [US2] Adjust `Evaluator.start()`'s background-thread body in
      `deepeval_platform/evaluation/evaluator.py` so `run.transition_to(IN_PROGRESS)` is called only
      once extraction completes and `run.set_total()` makes the total known, and
      `run.increment_processed()` is called
      immediately after each trace (success or isolated failure) rather than in a batch, so
      coherent `run.snapshot()` reads observe live progress. All methods/properties involved MUST
      synchronize through the run's state `RLock`; do not hold it while invoking collaborators
      (data-model.md State Transitions) — GREEN for T018, T019
      (depends on T017)
- [ ] T023 [US2] Verify/adjust `end_timestamp` assignment in
       `deepeval_platform/evaluation/evaluator.py` and `evaluation_run.py` so public
       `EvaluationRun.transition_to()` sets `end_timestamp` and signals `run.wait()` exactly once, the
       first time the run reaches any terminal `RunStatus` (including `DELIVERY_FAILED`); a later
       successful retry does not move the timestamp or clear the completion signal, and
       `DELIVERING` never sets either value (data-model.md)
        — GREEN for T020 (depends on T022). T021 becomes GREEN after T035 and MUST be rerun at that
        point; it is not a Phase 4 implementation prerequisite.

**Checkpoint**: User Stories 1 AND 2 both work independently — live progress observation confirmed
on top of the US1 pipeline.

---

## Phase 5: User Story 3 - A run survives failures in individual traces (Priority: P3)

**Goal**: A trace that fails during normalization or evaluation is isolated into a `PerTraceError`
without stopping the rest of the run; the run's final status distinguishes a fully clean
`COMPLETED` from `COMPLETED_WITH_FAILURES`.

**Independent Test**: Start a run over a period with one trace stubbed to fail (during
normalization or evaluation) and several that succeed; confirm the run still completes with
results for every non-failing trace and the failure recorded with `trace_id`/`stage`/`error_code`/
`message`.

### Tests for User Story 3 ⚠️

- [ ] T024 [US3] Add failing unit test in `tests/unit/evaluation/test_evaluator.py`: one stub
       trace raises during `TraceNormalizer.normalize()` and another raises during
       `EvaluationOrchestrator.evaluate()`, while the collector reports one identified
        trace-specific extraction failure; all three are isolated into `run.errors` with the
        stage-matched stable codes `extraction_failed`, `normalization_failed`, and
        `evaluation_failed` (message sanitized via existing `sanitize_error()`), `run.total` equals
        the combined count of successful traces and collection errors, `run.processed` still
        reaches that total, and every other trace still has
       an `EvaluationResult` published through `ResultPublisher`. Include the collector's already
       resolved duplicate-ID extraction error (with no successful trace for that ID) and assert it
       yields no result or overwrite while unique IDs retain their results (US3 Scenario 1, FR-006,
       FR-010). Use exceptions containing a bearer token and opaque credential and assert the public
       message contains a stable human-readable stage fallback with those sensitive values and raw
       exception text absent — run and observe RED
- [ ] T025 [US3] Add failing unit test in `tests/unit/evaluation/test_evaluator.py`: a run with
      zero `PerTraceError`s reaches `RunStatus.COMPLETED`; a run with one or more reaches
      `RunStatus.COMPLETED_WITH_FAILURES`; assert the two are distinct enum values (US3 Scenario 2,
      FR-011) — run and observe RED
- [ ] T026 [US3] Add failing unit test in `tests/unit/evaluation/test_evaluator.py`: a stub
       `TraceCollector.collect_all` that raises once yields `RunStatus.UNABLE_TO_RUN` with
       `run.end_timestamp` set, `run.wait(timeout)` returning `True`, a sanitized
        `run.failure_message`, and `run.total` staying `None`, distinguishing whole-run
        infrastructure failure from an isolated per-trace failure (Edge Cases, FR-011, research.md
        R5). Use an exception containing bearer/API-key/password/opaque credential material and
        assert raw exception text and every sensitive value are absent — run and observe RED
- [ ] T045 [US3] Add failing unit test in `tests/unit/evaluation/test_evaluator.py`: force an
       unexpected non-trace-specific exception to escape the worker's planned pipeline handling;
       assert `run.wait(timeout)` returns `True`, `run.status == UNABLE_TO_RUN`,
        `run.end_timestamp` is set, and `run.failure_message` is sanitized. Include bearer/API-key/
        password/opaque credential material and assert no raw exception or sensitive value is
        exposed (FR-011) — run and
        observe RED
- [ ] T054 [US3] Add failing unit tests in `tests/unit/evaluation/test_evaluator.py`: a returned
       `EvaluationResult` containing the orchestrator's supported metric-level error details remains
       in results without a `PerTraceError`, while an orchestrator exception creates exactly one
       `evaluation_failed`; also simulate thread creation/start failure and assert the accepted run
        reaches `UNABLE_TO_RUN` with a stable sanitized `failure_message`, terminal timestamp, and
        signaled wait rather than remaining `STARTED` — run and observe RED

### Implementation for User Story 3

- [ ] T027 [US3] Implement per-trace failure isolation in the background-thread body of
       `Evaluator.start()` (`deepeval_platform/evaluation/evaluator.py`): convert identified
       collector failures into extraction-stage `PerTraceError` entries through
       `run.append_error()`, and wrap each trace's normalize+evaluate steps in a try/except that
       passes a `PerTraceError` to `run.append_error()` with
        `PerTraceErrorCode.NORMALIZATION_FAILED` or `PerTraceErrorCode.EVALUATION_FAILED`, based
        on the failed stage, and a sanitized message. Convert collector failures with
         `PerTraceErrorCode.EXTRACTION_FAILED`; call `run.set_total()` with the combined count of
         successful traces and identified collection errors, and call `run.increment_processed()` once per identified
         collection error; never derive the code from `type(exc).__name__`.
        Continue to the next trace instead of stopping (FR-010) — GREEN for T024 (depends on T017,
        T022, T044)
- [ ] T028 [US3] Implement terminal-outcome selection in `Evaluator.start()`
       (`deepeval_platform/evaluation/evaluator.py`): after all traces are processed, choose
       `COMPLETED` if `run.errors` is empty or `COMPLETED_WITH_FAILURES` otherwise, retain that
       outcome for initial publication and retry, and let T035/T036 apply it through
       `run.complete_delivery()` only after successful publication (FR-011) — GREEN for T025
       (depends on T027)
- [ ] T029 [US3] Implement whole-run extraction-failure handling in `Evaluator.start()`
       (`deepeval_platform/evaluation/evaluator.py`): wrap `TraceCollector.collect_all()` so a setup,
       connectivity, or other non-trace-specific exception sets
       `run.set_failure_message(sanitize_error(exc))` and calls
       `run.transition_to(UNABLE_TO_RUN)`. Skip trace processing and publication entirely, ensure `run.total`
       remains `None`, and never expose raw exception or credential text (FR-011, research.md R5) —
       GREEN for T026 (depends on T017)
- [ ] T046 [US3] Wrap the worker entrypoint in `Evaluator.start()`
       (`deepeval_platform/evaluation/evaluator.py`) with an outer `except Exception` guard for
       errors that escape planned handling: call `run.set_failure_message(sanitize_error(exc))` and
       `run.transition_to(UNABLE_TO_RUN)`. Do not catch or reclassify
        identified per-trace failures; apply the same terminal sanitization path if worker startup
        fails (FR-010, FR-011) — GREEN for T045, T054 (depends on T017, T027,
       T029)

**Checkpoint**: All three user stories are independently functional — full pipeline, live progress,
and per-trace resilience all verified.

---

## Phase 6: Delivery Failure and Retry (cross-cutting on FR-007/SC-006/SC-007)

**Purpose**: Delivery-failure assertions and the explicit retry operation on top of the initial
`ResultPublisher`/`ResultObserver` publication implemented by T035
— required by all three stories' terminal-state contract (`DELIVERY_FAILED` is one of the four
statuses FR-011 requires distinguishable) but specified together here since retry has no
independent user story of its own; it is exercised through US1/US2's existing test scaffolding.

### Tests ⚠️

- [ ] T030 Add failing unit test in `tests/unit/evaluation/test_evaluator.py`: a stub
        `ResultPublisher.publish` that observes `DELIVERING` and raises once yields
       `run.status == DELIVERY_FAILED`,
       `run.end_timestamp` set, and `run.results` exposes the completed results for read-only
       inspection without exposing mutable internal storage. Before raising, have the observer
       attempt a mapping mutation and mutate a nested metric result in its snapshot; assert neither
       mutation changes a fresh `run.results` snapshot — run and observe RED (Edge Cases, FR-007,
       SC-006)
- [ ] T055 Add failing unit tests in `tests/unit/evaluation/test_evaluator.py`: successful initial
       publication and successful retry each expose no observable completed state that still retains
       the observer, proving completion plus observer release is one synchronized run-owned action;
       a zero-trace run publishes exactly one empty detached read-only mapping before reaching
       `COMPLETED` — run and observe RED (FR-007, SC-004)
- [ ] T031 Add failing unit tests for `Evaluator.retry_delivery()` in
       `tests/unit/evaluation/test_evaluator.py`: retry after a stub `publish` now succeeds
       transitions to `COMPLETED`/`COMPLETED_WITH_FAILURES` per the original trace outcome, and
        `publish` was called exactly twice total with no new extraction/normalization/evaluation
       calls recorded, both times for the run's original observer. Assert that a successful retry
       does not change the `end_timestamp` recorded when the run first entered `DELIVERY_FAILED`
       and does not clear or replace the completion signal. Assert the retry observer receives a
       fresh snapshot containing the original canonical values, unaffected by mutations attempted
       during the failed first delivery (Edge Cases, FR-007, FR-009, SC-007) —
       run and observe RED
- [ ] T032 Add failing unit test: `retry_delivery()` called on a `COMPLETED`/`IN_PROGRESS`/
      `DELIVERING`/`UNABLE_TO_RUN` run raises `InvalidRetryStateError` and leaves `run.status`
       unchanged. Capture snapshots before and after and assert status, counts, timestamps, errors,
       results, failure message, and completion signaling are unchanged (Edge Cases, FR-007) — run
       and observe RED
- [ ] T033 Add failing unit tests for concurrent delivery retries: while one `retry_delivery()`
       call is in flight for a `DELIVERY_FAILED` run, a second call raises `RetryInProgressError`
       immediately. If the active attempt fails and leaves the run `DELIVERY_FAILED`, a later retry
       may make one new publication attempt. If it succeeds and moves the run to `COMPLETED` or
       `COMPLETED_WITH_FAILURES`, a later retry raises `InvalidRetryStateError` and makes no
       publication attempt (Edge Cases, FR-007) — run and observe RED

### Implementation

- [ ] T036 Implement `Evaluator.retry_delivery(run: EvaluationRun)` in
      `deepeval_platform/evaluation/evaluator.py`: call `run.begin_retry()`, which atomically
      validates `DELIVERY_FAILED` and acquires the non-blocking retry guard under the state lock,
       raising `InvalidRetryStateError` or `RetryInProgressError` itself; unpack the payload and call
        `self._publisher.publish(run, results_snapshot, observer)` inside a `try/finally`. Retain
       `DELIVERY_FAILED` throughout the observer call (do not transition to `DELIVERING` during
        retry); on success, call `run.complete_delivery()` with `COMPLETED` or
        `COMPLETED_WITH_FAILURES` per `len(run.errors) == 0`, without moving the first end timestamp
        or clearing the completion signal. The `finally` block calls `run.end_retry()`, so the
         successful status transition and observer release occur before the retry guard is released;
         on failure leave
        `DELIVERY_FAILED` and still release the guard (research.md R6) —
          GREEN for T030, T031, T032, T033 and T055 (depends on T035)

**Checkpoint**: All four terminal statuses (FR-011) and the retry contract (FR-007) are fully
implemented and tested.

---

## Phase 7: Integration Verification

**Purpose**: Confirm the real repository → M2.1 → M2.2 → M3.1 → publisher composition test created
RED in T037 is GREEN after the complete implementation, per plan.md's Testing strategy.

- [ ] T039 Run `uv run pytest tests/integration/test_evaluator_flow_integration.py -v -rs -m
       integration` and require the credential-free local integration test to pass with zero
       skipped tests after the completed `Evaluator` implementation. Any skip, external network
       access, or credential dependency fails this gate (depends on T036)

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Final gates from quickstart.md before declaring the milestone done.

- [ ] T038 [P] Run `uv run pytest tests/unit/evaluation/test_evaluation_config.py
      tests/unit/evaluation/test_evaluation_run.py tests/unit/evaluation/test_evaluator.py
      tests/unit/evaluation/test_evaluation_orchestrator.py
      tests/unit/evaluation/metrics/test_metric_factory.py
      tests/unit/evaluation/test_result_publisher.py tests/unit/collection/test_trace_collector.py
      tests/unit/repositories/test_trace_repository.py -v` and confirm all pass
- [ ] T040 Run `uv run pytest --cov=deepeval_platform --cov-report=term-missing
      --cov-report=json --cov-fail-under=80`, confirm aggregate coverage remains at least 80%, and
      verify each new or changed module has at least 80% coverage: `evaluation_config.py`,
      `evaluation_run.py`, `result_publisher.py`, `evaluator.py`, `evaluation_orchestrator.py`,
      `metric_factory.py`, `errors.py`, `trace_collector.py`, and `trace_repository.py`
       (Constitution Principle IV and Quality Gate 2)
- [ ] T056 Run the feature unit and integration suites under the constitution's minimum supported
       Python 3.11 environment through the repository's `uv`/CI matrix, with no skips or syntax/
       dependency compatibility failures. Record both Python 3.11 and the development Python 3.13
       results (Constitution Technology Stack)
- [ ] T057 Inspect `git log --reverse --name-status` and the relevant test/production diffs to
       verify durable RED-before-GREEN evidence for every production task. Record the evidence in
       research.md's post-implementation gate status; if history does not prove a test preceded its
       implementation, the TDD gate fails and the feature MUST NOT be declared complete
       (Constitution Principle IV and Quality Gate 1)
- [ ] T048 Run `uv run detect-secrets scan --all-files` if `detect-secrets` is already available in
       the project; otherwise run `git diff --check` plus `rg -n -i
       '(api[_-]?key|secret|token|password|bearer)\s*[:=]\s*["'"'][^"'"']+["'"']|https?://(?!127\.0\.0\.1|localhost)'
       deepeval_platform/evaluation deepeval_platform/collection deepeval_platform/repositories
       tests/unit/evaluation tests/unit/collection tests/unit/repositories tests/integration` and
       review every match. The gate passes only when no real API key, token, password, credential
       value, non-local environment-specific host, or sensitive exception text is present and all
       configuration access continues through `ConfigManager` (Constitution Principle V and Quality
       Gate 3)
- [ ] T041 Update research.md's "Post-implementation gate status" section (currently "Not yet
      started") to record actual pass/fail status per the M4.1 precedent. Explicitly reconfirm that
      implementation preserved the documented DeepEval-first boundary: native metrics perform all
      scoring and `Evaluator` contains only the lifecycle capabilities identified as absent from
      DeepEval 4.0.7

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies
- **Foundational (Phase 2)**: Depends on Setup — BLOCKS all user stories (new error classes and the
  public metric-registration query are used by validation/retry paths)
- **User Story 1 (Phase 3)**: Depends on Foundational. Its extraction/evaluation implementation has
  no dependency on US2/US3; its final checkpoint is reached only after T028 selects the outcome and
  T035 performs initial publication.
- **User Story 2 (Phase 4)**: Depends on Foundational + US1's `Evaluator.start()`/`EvaluationRun`
  existing (it refines the same background-thread body) — not independently implementable before
  US1's core pipeline exists, but independently *testable* once it does
- **User Story 3 (Phase 5)**: Depends on Foundational + US1 (same reason as US2) — independent of
  US2
- **Phase 6 (Publication/Retry)**: Depends on initial publication T035 and the completed
  US1/US2/US3 background-thread behavior; this phase adds delivery-failure assertions and retry.
- **Phase 7 (Integration Verification)**: Depends on Phase 6 complete; the integration test itself
  was already written and observed RED in T037 before production implementation
- **Phase 8 (Polish)**: Depends on all above; T056 and T057 are mandatory completion gates

### Within Each User Story

- Tests MUST be written, run, and observed failing (RED) before their corresponding implementation
  task
- `EvaluationConfig`/`EvaluationRun`/`RunStatus`/`PerTraceError` (models) before `Evaluator`
  (orchestrator)
- Core pipeline (US1) before progress refinement (US2) and failure isolation (US3), since both
  refine the same background-thread body US1 introduces

### Parallel Opportunities

- T002 and T049 can run in parallel; T003 follows T002 and T050 follows T049
- T004, T005, T011, T042, T043, T049, and T051 can run in parallel because they modify different
  files; T006 follows T013, and T007 follows the minimal importable model/interface implementations
  T012/T014/T034/T050, then must be executed RED before T016. T008-T010, T047, and T053 share test
  files and run sequentially before T017. T037 is the final all-flow RED gate before T015-T017,
  T035, T044, or T052; T052 follows T051/T037, T044 follows T043/T052/T037, and T035 follows
  T017/T028
- T012, T013 (different files: `evaluation_config.py` vs. `evaluation_run.py`) can run in parallel
- T018-T021, T024-T026/T045/T054, and T030-T033/T055 share `test_evaluator.py` and must run sequentially

---

## Parallel Example: User Story 1

```bash
# Launch independent-file tests for User Story 1 together:
Task: "Add failing unit tests for EvaluationConfig in tests/unit/evaluation/test_evaluation_config.py"
Task: "Add failing unit tests for EvaluationOrchestrator's thresholds override in tests/unit/evaluation/test_evaluation_orchestrator.py"

# Launch independent-file models together once tests are RED:
Task: "Implement EvaluationConfig dataclass in deepeval_platform/evaluation/evaluation_config.py"
Task: "Implement RunStatus and PerTraceError in deepeval_platform/evaluation/evaluation_run.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (new error classes)
3. Execute each unit test RED as soon as its import prerequisites exist, then execute T037 RED
   before any production implementation covered by the integration flow
4. Complete the Phase 3 pipeline, T028 outcome selection, and T035 initial publication so User
   Story 1 reaches `COMPLETED` through the real pipeline composition (stubbed collaborators)
5. **STOP and VALIDATE**: Run `tests/unit/evaluation/test_evaluator.py`'s US1 subset independently
6. Note: `RunStatus.DELIVERY_FAILED` and `retry_delivery()` (Phase 6) are required for FR-011's
   full four-way status distinction — MVP scope should include Phase 6 before calling M4.2 "done,"
   even though US1's independent test above only exercises the `COMPLETED` path

### Incremental Delivery

1. Setup + Foundational → foundation ready
2. US1 → full pipeline including initial successful publication, `COMPLETED` reachable → validate independently
3. US2 → live progress observation on the same handle → validate independently
4. US3 → per-trace isolation, `COMPLETED_WITH_FAILURES` → validate independently
5. Phase 6 → `DELIVERY_FAILED` + retry → completes FR-011's four-way status contract
6. Phase 7 → confirm the real composition integration test created in T037 is GREEN
7. Phase 8 → coverage gate + polish

### Parallel Team Strategy

Given US2 and US3 both extend the same `Evaluator.start()` background-thread body introduced in
US1, true parallel team execution across US2/US3 requires coordinating edits to the same method in
`evaluator.py` and the shared `test_evaluator.py`; implement and test each phase sequentially once
US1 is complete.

---

## Notes

- [P] tasks = different files with no dependencies on incomplete tasks
- [Story] label maps task to specific user story for traceability
- Every implementation task names the exact test task(s) it turns GREEN
- Commit after each task or logical group
- Stop at any checkpoint to validate a story independently
- No `contracts/` HTTP schema tasks — this milestone's only "contract" is the internal Python API
  in `contracts/evaluator-api.md`, already covered by the `Evaluator`/`EvaluationConfig` test tasks
  above

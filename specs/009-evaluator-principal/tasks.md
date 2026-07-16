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
- Integration tests: `tests/integration/`

---

## Phase 1: Setup

**Purpose**: No new project scaffolding is required — `deepeval_platform/evaluation/` and
`tests/unit/evaluation/`/`tests/integration/` already exist (M3.1/M4.1). This phase only confirms
the ground is ready.

- [ ] T001 Confirm `uv run pytest tests/unit/evaluation/test_evaluation_orchestrator.py -v` and
      `uv run pytest --cov=deepeval_platform --cov-report=term-missing --cov-fail-under=80` both
      pass on the current branch before any new code is added (establishes the pre-change baseline
      quickstart.md's coverage gate compares against)

**Checkpoint**: Baseline green; safe to add new files.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: New exception classes that every user story's validation and retry paths depend on.
No test/implementation in Phase 3+ can reference these until they exist.

**⚠️ CRITICAL**: Must complete before any user story work begins.

- [ ] T002 [P] Add failing unit tests for `UnknownBotError`, `InvalidPeriodError`,
      `InvalidRetryStateError`, `RetryInProgressError` (message/attribute shape, per research.md R4
      and data-model.md) in `tests/unit/evaluation/test_errors.py` — run and observe RED
- [ ] T003 Add `UnknownBotError`, `InvalidPeriodError`, `InvalidRetryStateError`,
      `RetryInProgressError` to `deepeval_platform/evaluation/errors.py`, following the file's
      existing `EvaluationOrchestratorError` subclass convention (each carries every diagnostic
      field a caller needs, per research.md R4/R6) — GREEN for T002 (depends on T002)

**Checkpoint**: Foundational error types exist; user story implementation can begin.

---

## Phase 3: User Story 1 - Trigger a full evaluation run for a bot (Priority: P1) 🎯 MVP

**Goal**: A caller supplies `bot_id`, metrics/thresholds, and a period; `Evaluator.start()`
validates the config, extracts/normalizes/evaluates every trace in the period, and delivers
results through `ResultHandoff`, reaching `COMPLETED` (or `COMPLETED_WITH_FAILURES` if a trace
failed — covered fully in US3, but the terminal-status distinction must exist by the end of this
phase since `RunStatus` is defined here).

**Independent Test**: Start a run for a bot with known stub traces in a known period (via stubbed
`TraceCollector`/`TraceNormalizer`/`EvaluationOrchestrator`/`ResultHandoff`) and confirm the run
reaches `COMPLETED` with one `EvaluationResult` per trace recorded by the stub handoff — no US2/US3
capability required.

### Tests for User Story 1 ⚠️

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [ ] T004 [P] [US1] Add failing unit tests for `EvaluationConfig` in
      `tests/unit/evaluation/test_evaluation_config.py`: UTC normalization of naive/aware
      `period_start`/`period_end` (research.md R7), `InvalidPeriodError` when `period_end` is not
      strictly later than `period_start` (raised in `__post_init__`, no collaborator needed) — run
      and observe RED
- [ ] T005 [P] [US1] Add failing unit tests for `RunStatus`/`PerTraceError` in
      `tests/unit/evaluation/test_evaluation_run.py`: `RunStatus` has exactly the six values from
      data-model.md; `PerTraceError` holds `trace_id`/`stage`/`error_code`/`message` — run and
      observe RED
- [ ] T006 [P] [US1] Add failing unit tests for `EvaluationRun` in
      `tests/unit/evaluation/test_evaluation_run.py`: `id` is a fresh `uuid4()` per instance,
      `processed`/`total`/`errors` default correctly, `progress` is `None` while `total is None`,
      `1.0` when `total == 0`, else `processed / total` (FR-008) — run and observe RED (depends on
      T005 existing in the same file)
- [ ] T007 [P] [US1] Add failing unit tests for `Evaluator.start()` pre-condition validation in
      `tests/unit/evaluation/test_evaluator.py`: empty `metric_thresholds` → `EmptyMetricListError`,
      unregistered metric → `UnknownMetricError`, out-of-range threshold → `InvalidThresholdError`,
      unknown `bot_id` → `UnknownBotError` — assert no `EvaluationRun` is ever constructed for any
      of these (use a stubbed `ConfigManager`/`MetricFactory`) — run and observe RED
- [ ] T008 [US1] Add failing unit tests for `Evaluator.start()` happy-path orchestration in
      `tests/unit/evaluation/test_evaluator.py`: stubbed `TraceCollector` returns N traces, stubbed
      `TraceNormalizer`/`EvaluationOrchestrator` succeed for each, stubbed `ResultHandoff.deliver`
      records `(run, results)` and succeeds → `run.status == COMPLETED`, `run.processed == N`,
      `run.total == N`, `run.end_timestamp` set once — run and observe RED (depends on T007 in the
      same file)
- [ ] T009 [P] [US1] Add failing unit test for zero-trace period in
      `tests/unit/evaluation/test_evaluator.py`: stubbed `TraceCollector` returns an empty list →
      `run.total == 0`, `run.progress == 1.0`, `run.status == COMPLETED`, no error recorded (US1
      Scenario 2, SC-004) — run and observe RED
- [ ] T010 [P] [US1] Add failing unit test for independent concurrent runs in
      `tests/unit/evaluation/test_evaluator.py`: two `start()` calls (different bots/periods) via a
      slow stub collector yield distinct `run.id`s with independently correct terminal state and
      overlapping thread lifetimes (US1 Scenario 3, FR-012) — run and observe RED
- [ ] T011 [P] [US1] Add failing unit tests for `EvaluationOrchestrator.evaluate()`'s new optional
      `thresholds` keyword parameter in `tests/unit/evaluation/test_evaluation_orchestrator.py`:
      when provided, scoring uses the override instead of the `bots.yaml`-resolved threshold; when
      omitted, existing config-lookup behavior is unchanged (research.md R3, FR-013) — run and
      observe RED

### Implementation for User Story 1

- [ ] T012 [P] [US1] Implement `EvaluationConfig` dataclass in
      `deepeval_platform/evaluation/evaluation_config.py`: `bot_id: str`, `metric_thresholds:
      dict[str, float]`, `period_start`/`period_end: datetime`, with `__post_init__` UTC
      normalization and eager `InvalidPeriodError` check (data-model.md, research.md R7) — GREEN
      for T004 (depends on T003 for `InvalidPeriodError`)
- [ ] T013 [P] [US1] Implement `RunStatus(str, Enum)` and `PerTraceError` dataclass in
      `deepeval_platform/evaluation/evaluation_run.py` (data-model.md) — GREEN for T005 (depends on
      T003)
- [ ] T014 [US1] Implement `EvaluationRun` dataclass in
      `deepeval_platform/evaluation/evaluation_run.py`: `id`, `status`, `processed`, `total`,
      `start_timestamp`, `end_timestamp`, `errors`, private `_results`/`_retry_lock` (excluded from
      `repr`/equality), derived `progress` property (data-model.md) — GREEN for T006 (depends on
      T013)
- [ ] T015 [US1] Add the optional keyword-only `thresholds: dict[str, float] | None = None`
      parameter to `EvaluationOrchestrator.evaluate()` in
      `deepeval_platform/evaluation/evaluation_orchestrator.py`, routing `_resolve_thresholds` to
      use it directly when provided instead of reading `bots.yaml` (research.md R3) — GREEN for
      T011
- [ ] T016 [US1] Implement `Evaluator.__init__` and `Evaluator.start()` pre-condition validation in
      `deepeval_platform/evaluation/evaluator.py`: validate `metric_thresholds` non-empty, every
      metric known to `MetricFactory`, every threshold in `[0.0, 1.0]`, `bot_id` configured via
      `ConfigManager.instance().get(f"bots.{bot_id}.bot_type")` catching `ConfigError` →
      `UnknownBotError` (research.md R4) — GREEN for T007 (depends on T012, T014, T003)
- [ ] T017 [US1] Implement `Evaluator.start()`'s run creation and background-thread orchestration in
      `deepeval_platform/evaluation/evaluator.py`: on successful validation, construct
      `EvaluationRun`, spawn a daemon `threading.Thread` that calls `TraceCollector.collect()`,
      then per trace calls `TraceNormalizer.normalize()` and
      `asyncio.run(EvaluationOrchestrator.evaluate(..., thresholds=config.metric_thresholds))`,
      accumulating `results`, then `ResultHandoff.deliver(run, results)`, setting terminal
      `run.status`/`run.end_timestamp`; return the run object immediately (research.md R2) — GREEN
      for T008, T009, T010 (depends on T016, T015)

**Checkpoint**: User Story 1 is fully functional and independently testable — a full run reaches a
terminal status through the real pipeline composition (stubbed collaborators).

---

## Phase 4: User Story 2 - Observe the status of an in-progress run (Priority: P2)

**Goal**: While a run executes, its already-returned `EvaluationRun` handle reflects live
`status`/`processed`/`total`/`progress`/timestamps without any separate polling API.

**Independent Test**: Start a run and, before it finishes, read the same handle's `status` and
`processed`/`total` to confirm they reflect an in-progress state and increase as traces are
processed, using only the US1 `Evaluator`/`EvaluationRun` machinery already built.

### Tests for User Story 2 ⚠️

- [ ] T018 [P] [US2] Add failing unit test in `tests/unit/evaluation/test_evaluator.py`: immediately
      after `start()` returns (before the background thread has progressed), `run.status` is
      `STARTED` (or already `IN_PROGRESS`), `run.processed == 0`, and `run.total is None` if
      extraction has not yet completed (US2 Scenario 1) — run and observe RED
- [ ] T019 [P] [US2] Add failing unit test in `tests/unit/evaluation/test_evaluator.py`, using a
      stub collector/orchestrator with an artificial delay per trace: while the run is partway
      through, `run.processed` reflects traces already processed and `run.total` reflects the
      discovered trace count (US2 Scenario 2, FR-008) — run and observe RED
- [ ] T020 [P] [US2] Add failing unit test in `tests/unit/evaluation/test_evaluator.py`: once a run
      reaches a terminal status, `run.start_timestamp` and `run.end_timestamp` are both set, with
      `end_timestamp` set exactly once even if a later retry succeeds (US2 Scenario 3, FR-009,
      data-model.md's end-timestamp rule) — run and observe RED
- [ ] T021 [P] [US2] Add failing unit test in `tests/unit/evaluation/test_evaluator.py` asserting
      `start()` returns before the stubbed pipeline's `deliver` call has been reached, i.e. the
      returned object's `status` is observed to change on a *second* read without any second call
      to `Evaluator` (US2 Scenario 4, FR-003) — run and observe RED

### Implementation for User Story 2

- [ ] T022 [US2] Adjust `Evaluator.start()`'s background-thread body in
      `deepeval_platform/evaluation/evaluator.py` so `run.status` transitions to `IN_PROGRESS` only
      once extraction completes and `run.total` becomes known, and `run.processed` is incremented
      immediately after each trace (success or isolated failure) rather than in a batch, so
      mid-run reads observe live progress (data-model.md State Transitions) — GREEN for T018, T019
      (depends on T017)
- [ ] T023 [US2] Verify/adjust `end_timestamp` assignment in
      `deepeval_platform/evaluation/evaluator.py` and `evaluation_run.py` so it is set exactly once,
      the first time the run reaches any terminal `RunStatus` (including `DELIVERY_FAILED`), and a
      later successful retry does not move it (data-model.md) — GREEN for T020 (depends on T022)

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

- [ ] T024 [P] [US3] Add failing unit test in `tests/unit/evaluation/test_evaluator.py`: one stub
      trace raises during `TraceNormalizer.normalize()` and another raises during
      `EvaluationOrchestrator.evaluate()`; both are isolated into `run.errors` with
      `trace_id`/`stage`/`error_code`/`message` populated (message sanitized via existing
      `sanitize_error()`), `run.processed` still reaches the total, and every other trace still has
      an `EvaluationResult` delivered to `ResultHandoff` (US3 Scenario 1, FR-010) — run and observe
      RED
- [ ] T025 [P] [US3] Add failing unit test in `tests/unit/evaluation/test_evaluator.py`: a run with
      zero `PerTraceError`s reaches `RunStatus.COMPLETED`; a run with one or more reaches
      `RunStatus.COMPLETED_WITH_FAILURES`; assert the two are distinct enum values (US3 Scenario 2,
      FR-011) — run and observe RED
- [ ] T026 [P] [US3] Add failing unit test in `tests/unit/evaluation/test_evaluator.py`: a stub
      `TraceCollector.collect` that raises once yields `RunStatus.UNABLE_TO_RUN` with
      `run.end_timestamp` set and `run.total` staying `None`, distinguishing whole-run
      infrastructure failure from an isolated per-trace failure (Edge Cases, FR-011, research.md
      R5) — run and observe RED

### Implementation for User Story 3

- [ ] T027 [US3] Implement per-trace failure isolation in the background-thread body of
      `Evaluator.start()` (`deepeval_platform/evaluation/evaluator.py`): wrap each trace's
      normalize+evaluate steps in a try/except that appends a `PerTraceError(trace_id, stage,
      type(exc).__name__, sanitize_error(exc))` to `run.errors` and continues to the next trace
      instead of stopping (FR-010) — GREEN for T024 (depends on T017, T022)
- [ ] T028 [US3] Implement terminal-status selection in `Evaluator.start()`
      (`deepeval_platform/evaluation/evaluator.py`): after all traces are processed and handoff
      succeeds, set `run.status = COMPLETED` if `run.errors` is empty else
      `COMPLETED_WITH_FAILURES` (FR-011) — GREEN for T025 (depends on T027)
- [ ] T029 [US3] Implement whole-run extraction-failure handling in `Evaluator.start()`
      (`deepeval_platform/evaluation/evaluator.py`): wrap the `TraceCollector.collect()` call so any
      exception sets `run.status = UNABLE_TO_RUN` and `run.end_timestamp`, skipping trace processing
      and handoff entirely (FR-011, research.md R5) — GREEN for T026 (depends on T017)

**Checkpoint**: All three user stories are independently functional — full pipeline, live progress,
and per-trace resilience all verified.

---

## Phase 6: Result Handoff and Retry (cross-cutting on FR-007/SC-006/SC-007)

**Purpose**: `ResultHandoff` interface, delivery-failure handling, and the explicit retry operation
— required by all three stories' terminal-state contract (`DELIVERY_FAILED` is one of the four
statuses FR-011 requires distinguishable) but specified together here since retry has no
independent user story of its own; it is exercised through US1/US2's existing test scaffolding.

### Tests ⚠️

- [ ] T030 [P] Add failing unit test in `tests/unit/evaluation/test_evaluator.py`: a stub
      `ResultHandoff.deliver` that raises once yields `run.status == DELIVERY_FAILED`,
      `run.end_timestamp` set, and `run._results` populated and inspectable (Edge Cases, FR-007,
      SC-006) — run and observe RED
- [ ] T031 [P] Add failing unit tests for `Evaluator.retry_delivery()` in
      `tests/unit/evaluation/test_evaluator.py`: retry after a stub `deliver` now succeeds
      transitions to `COMPLETED`/`COMPLETED_WITH_FAILURES` per the original trace outcome, and
      `deliver` was called exactly twice total with no new extraction/normalization/evaluation
      calls recorded (Edge Cases, FR-007, SC-007) — run and observe RED
- [ ] T032 [P] Add failing unit test: `retry_delivery()` called on a `COMPLETED`/`IN_PROGRESS`/
      `UNABLE_TO_RUN` run raises `InvalidRetryStateError` and leaves `run.status` unchanged (Edge
      Cases, FR-007) — run and observe RED
- [ ] T033 [P] Add failing unit test: two concurrent `retry_delivery()` calls on the same
      `DELIVERY_FAILED` run — one proceeds, the other raises `RetryInProgressError` immediately
      without waiting for the first to finish (Edge Cases, FR-007) — run and observe RED

### Implementation

- [ ] T034 [P] Implement `ResultHandoff` ABC in
      `deepeval_platform/evaluation/result_handoff.py`: single abstract method `deliver(self, run:
      EvaluationRun, results: dict[str, EvaluationResult]) -> None` (data-model.md, research.md R6)
      — no test dependency, needed before T035/T036 compile (depends on T014)
- [ ] T035 Implement delivery-failure handling in `Evaluator.start()`'s background-thread body
      (`deepeval_platform/evaluation/evaluator.py`): call `self._handoff.deliver(run, results)`
      after trace processing; on exception, store `results` in `run._results`, set `run.status =
      DELIVERY_FAILED` and `run.end_timestamp` (research.md R6) — GREEN for T030 (depends on T034,
      T028, T029)
- [ ] T036 Implement `Evaluator.retry_delivery(run: EvaluationRun)` in
      `deepeval_platform/evaluation/evaluator.py`: validate `run.status is
      RunStatus.DELIVERY_FAILED` else raise `InvalidRetryStateError`; acquire
      `run._retry_lock` non-blocking else raise `RetryInProgressError`; call
      `self._handoff.deliver(run, run._results)` again; on success set `run.status` to `COMPLETED`
      or `COMPLETED_WITH_FAILURES` per `len(run.errors) == 0`, else leave `DELIVERY_FAILED`
      (research.md R6) — GREEN for T031, T032, T033 (depends on T035)

**Checkpoint**: All four terminal statuses (FR-011) and the retry contract (FR-007) are fully
implemented and tested.

---

## Phase 7: Integration Test

**Purpose**: Exercise the real M2.1 → M2.2 → M3.1 composition (not stubs) end to end, per plan.md's
Testing strategy.

- [ ] T037 Add `tests/integration/test_evaluator_flow_integration.py` (marked `-m integration`),
      following the skip-with-reason convention already used by the M4.1 integration suite when
      live credentials are absent: exercise `Evaluator.start()` against a real `TraceCollector` →
      `TraceNormalizer` → `EvaluationOrchestrator` composition with local/stub Langfuse fixtures for
      a configured test bot, asserting the run reaches `COMPLETED` with one `EvaluationResult` per
      fixture trace via a simple in-memory `ResultHandoff` (quickstart.md) — run and observe RED,
      then confirm GREEN against the completed `Evaluator` implementation (depends on T036)

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Final gates from quickstart.md before declaring the milestone done.

- [ ] T038 [P] Run `uv run pytest tests/unit/evaluation/test_evaluation_config.py
      tests/unit/evaluation/test_evaluation_run.py tests/unit/evaluation/test_evaluator.py
      tests/unit/evaluation/test_evaluation_orchestrator.py -v` and confirm all pass
- [ ] T039 [P] Run `uv run pytest tests/integration/test_evaluator_flow_integration.py -v -m
      integration` and confirm pass or documented skip-with-reason
- [ ] T040 Run `uv run pytest --cov=deepeval_platform --cov-report=term-missing
      --cov-fail-under=80` and confirm the >=80% coverage gate holds (Constitution Principle IV)
- [ ] T041 Update research.md's "Post-implementation gate status" section (currently "Not yet
      started") to record actual pass/fail status per the M4.1 precedent (research.md line 202-205)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies
- **Foundational (Phase 2)**: Depends on Setup — BLOCKS all user stories (new error classes used by
  every story's validation/retry paths)
- **User Story 1 (Phase 3)**: Depends on Foundational. No dependency on US2/US3.
- **User Story 2 (Phase 4)**: Depends on Foundational + US1's `Evaluator.start()`/`EvaluationRun`
  existing (it refines the same background-thread body) — not independently implementable before
  US1's core pipeline exists, but independently *testable* once it does
- **User Story 3 (Phase 5)**: Depends on Foundational + US1 (same reason as US2) — independent of
  US2
- **Phase 6 (Handoff/Retry)**: Depends on US1/US2/US3's background-thread body existing (adds the
  handoff call and retry operation on top)
- **Phase 7 (Integration)**: Depends on Phase 6 complete
- **Phase 8 (Polish)**: Depends on all above

### Within Each User Story

- Tests MUST be written, run, and observed failing (RED) before their corresponding implementation
  task
- `EvaluationConfig`/`EvaluationRun`/`RunStatus`/`PerTraceError` (models) before `Evaluator`
  (orchestrator)
- Core pipeline (US1) before progress refinement (US2) and failure isolation (US3), since both
  refine the same background-thread body US1 introduces

### Parallel Opportunities

- T002 (Foundational tests) can run alone; T003 follows
- T004, T005, T007, T009, T010, T011 (different test concerns, though some share
  `test_evaluator.py`/`test_evaluation_run.py` — treat file-sharing tasks as sequential within that
  file even though marked [P] for conceptual independence; a single developer should write them in
  sequence within the same file)
- T012, T013 (different files: `evaluation_config.py` vs. `evaluation_run.py`) can run in parallel
- T018-T021, T024-T026, T030-T033 similarly share test files within their phase — parallelizable
  across developers working in different phases, sequential within one file for one developer

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
3. Complete Phase 3: User Story 1 — a full run reaches `COMPLETED` through the real pipeline
   composition (stubbed collaborators)
4. **STOP and VALIDATE**: Run `tests/unit/evaluation/test_evaluator.py`'s US1 subset independently
5. Note: `RunStatus.DELIVERY_FAILED` and `retry_delivery()` (Phase 6) are required for FR-011's
   full four-way status distinction — MVP scope should include Phase 6 before calling M4.2 "done,"
   even though US1's independent test above only exercises the `COMPLETED` path

### Incremental Delivery

1. Setup + Foundational → foundation ready
2. US1 → full pipeline, `COMPLETED` reachable → validate independently
3. US2 → live progress observation on the same handle → validate independently
4. US3 → per-trace isolation, `COMPLETED_WITH_FAILURES` → validate independently
5. Phase 6 → `DELIVERY_FAILED` + retry → completes FR-011's four-way status contract
6. Phase 7 → real composition integration test
7. Phase 8 → coverage gate + polish

### Parallel Team Strategy

Given US2 and US3 both extend the same `Evaluator.start()` background-thread body introduced in
US1, true parallel team execution across US2/US3 requires coordinating edits to the same method in
`evaluator.py` — recommend implementing US1 first, then splitting US2/US3 test-writing in parallel
while implementation lands sequentially against the shared file.

---

## Notes

- [P] tasks = different files, no dependencies — but see the file-sharing caveat under Parallel
  Opportunities for tasks that share `test_evaluator.py`/`test_evaluation_run.py`
- [Story] label maps task to specific user story for traceability
- Every implementation task names the exact test task(s) it turns GREEN
- Commit after each task or logical group
- Stop at any checkpoint to validate a story independently
- No `contracts/` HTTP schema tasks — this milestone's only "contract" is the internal Python API
  in `contracts/evaluator-api.md`, already covered by the `Evaluator`/`EvaluationConfig` test tasks
  above

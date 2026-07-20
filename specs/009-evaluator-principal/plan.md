# Implementation Plan: Evaluator Principal

**Branch**: `009-evaluator-principal` | **Date**: 2026-07-16 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/009-evaluator-principal/spec.md`

## Summary

M4.2 adds `deepeval_platform/evaluation/evaluator.py` — a facade orchestrating one full
extract-normalize-evaluate-publish run for a bot/period, on top of the already-implemented M2.1
`TraceCollector`, M2.2 `TraceNormalizer`, and M3.1 `EvaluationOrchestrator`. `EvaluationConfig`
(`evaluation/evaluation_config.py`) stores submitted metric-threshold entries as
`list[MetricThreshold]` until FR-015 duplicate-name validation completes, then `Evaluator.start()`
builds an internal `dict[str, float]` for evaluation (research.md R1). `Evaluator.start()`
validates synchronously (unknown metric, non-numeric/non-finite/out-of-range threshold, unknown bot,
invalid period — no
partial state on failure), creates an `EvaluationRun` (`evaluation/evaluation_run.py`, UUID-keyed,
mutable behind a per-run `threading.RLock`, with synchronized properties and immutable
`EvaluationRunSnapshot` values), and returns it immediately while a background `threading.Thread`
updates that same object through its public methods (research.md R2). Its `wait(timeout)` method uses a per-run completion event, so callers can await the first
terminal state without polling — there is no server-side run registry or `get_run(id)` API; the
object the caller already holds *is* the queryable state (research.md R6). Per-trace failures during normalization or
evaluation become isolated `PerTraceError` entries and never stop the remaining traces (FR-010);
setup failures and unexpected worker-level failures that cannot identify a trace route to
   `UNABLE_TO_RUN` with a sanitized run-level diagnostic instead. Identified extraction failures
   count toward the run's fixed total and processed counts, so a terminal run has processed every
   successful or failed trace outcome. `EvaluationOrchestrator.
evaluate()` gains an additive, optional `thresholds` override parameter so a run's config can
override a bot's `bots.yaml` defaults for that run only, without `Evaluator` duplicating the
orchestrator's threshold/timeout/judge resolution (research.md R3). Completed results are published
only to the `ResultObserver` supplied to `Evaluator.start()` for that run, through a new
`ResultPublisher` Observer interface (`evaluation/result_publisher.py`) — this
   milestone defines the publisher and observer contract only, per the spec's explicit scope boundary;
   after evaluation, the run enters non-final `DELIVERING` before the observer is called; a
   successful call reaches `COMPLETED`/`COMPLETED_WITH_FAILURES`, while a failed publication transitions
   the run to `DELIVERY_FAILED` while retaining its in-memory results on the run object itself;
   `EvaluationRun.results` exposes a read-only snapshot for requester inspection.
   `EvaluationRun.delivery_payload()` returns exactly `(results_snapshot, observer)`, so both the
   initial attempt and `Evaluator.retry_delivery(run)` call
   `ResultPublisher.publish(run, results_snapshot, observer)`. Retry repeats only publication to
   that same observer, serialized per-run
via a lock stored on the run (research.md R6).

## Technical Context

**Language/Version**: Python 3.13 in this repository; constitution minimum Python `^3.11`.

**Primary Dependencies**:
- Existing `deepeval_platform.collection.trace_collector.TraceCollector` (M2.1) for extraction —
  extended with an additive exhaustive `collect_all()` operation that returns identified per-trace
  extraction failures alongside successfully extracted traces, while retaining a whole-run
  exception for setup/connectivity failures. Existing capped `collect()` behavior remains
  unchanged. `TraceRepository` gains an additive paginated date-range operation so `collect_all()`
  can satisfy FR-004 beyond 500 traces (research.md R8).
- Existing `deepeval_platform.normalization.trace_normalizer.TraceNormalizer` (M2.2) for
  per-trace normalization — unchanged.
- Existing `deepeval_platform.evaluation.evaluation_orchestrator.EvaluationOrchestrator` (M3.1)
  for per-trace metric evaluation — extended with one additive optional parameter (research.md
  R3), no breaking change to its existing signature/tests.
- Existing `deepeval_platform.evaluation.metrics.metric_factory.MetricFactory` for metric-name
  validation through a new public `is_registered(name)` query, preserving registry encapsulation
  while reusing the exact membership check `EvaluationOrchestrator` already performs.
- Existing `deepeval_platform.config.config_manager.ConfigManager` — sole config reader, used only
  for the `bots.{bot_id}.bot_type` existence check. Only the manager's explicit missing-key outcome
  or an empty returned value means the bot is unknown and becomes `UnknownBotError`;
  configuration-loading/parsing failures propagate and never become invalid-user-input errors.
- Stdlib only for the new orchestration itself: `threading` (background execution + retry
  serialization), `asyncio` (driving `EvaluationOrchestrator.evaluate()` per trace from a sync
  thread), `uuid`, `dataclasses`, `enum`. No new third-party dependency.

**Configuration**: None new. No new `bots.yaml`/`settings.yaml` keys, no new `.env` variable —
`Evaluator` composes already-configured collaborators and validates `bot_id` existence through the
same `ConfigManager` key (`bots.{bot_id}.bot_type`) `TraceNormalizer` already depends on.

**Storage**: N/A for this milestone. `EvaluationRun`/results are in-memory only, living as long as
the caller holds the returned handle (research.md R6). Durable persistence
(`EvaluationRepository`) is out of scope per the spec's Assumptions/Clarifications.

**Testing**: Strict TDD. For every behavior, write the test and observe RED before production
code, then GREEN, then refactor while green. Unit tests stub `TraceCollector`, `TraceNormalizer`,
`EvaluationOrchestrator`, and `ResultPublisher` at the `Evaluator` boundary. One `-m integration`
test exercises the real repository→M2.1→M2.2→M3.1→publisher composition against a local HTTP
server that implements the paginated Langfuse trace-response contract. Only the external LLM
boundary is replaced by a deterministic `DeepEvalBaseLLM` fake. The test requires no live service,
external network access, or credentials and MUST pass without `skip`, `skipif`, or
environment-dependent branching.

**Constraints**:
- No partial `EvaluationRun` state is ever created for an invalid `EvaluationConfig` (FR-002).
- `bots.yaml` is never mutated by a run's threshold overrides (FR-013).
- Caller thresholds accept only non-boolean `int`/`float` values satisfying
  `math.isfinite(float(value)) and 0.0 <= float(value) <= 1.0`; strings are not coerced, and valid
  values are converted to float only after all entries pass validation (FR-002).
- Period boundaries must be `datetime` values. Naive values are interpreted as UTC; aware values
  are converted to UTC. Bot IDs and metric names must contain at least one non-whitespace character.
- A per-trace failure never stops the remaining traces in the run (FR-010, SC-002).
- `start()` returns before processing completes; the returned object is later mutated in place,
   never replaced (FR-003, US2 Scenario 4).
- Identified extraction failures count toward both `total` and `processed`; once extraction
  completes, `total` is successful traces plus identified extraction failures (FR-008).
- `TraceCollectionResult` enforces one outcome per trace ID. Duplicate IDs are collapsed into one
  extraction error with no successful record for that ID, so the evaluator's result mapping can
  never overwrite an earlier logical trace result (FR-006/FR-010).
- Empty or whitespace-only trace identifiers invalidate exhaustive collection and produce a
  whole-run `UNABLE_TO_RUN`; no synthetic identifier is generated.
- Evaluation runs use `TraceCollector.collect_all()` and never the M2.1 capped `collect()` method;
  repository pages are exhausted and the UTC `[start, end)` boundary is rechecked locally before
  evaluation. The exhaustive repository request uses one implementation-owned fixed page-size
  constant and ascending `(trace timestamp, trace_id)` ordering on every page. The page size is an
  internal protocol batching detail rather than an environment setting and cannot affect result
  membership. The repository rejects records lacking either ordering component as malformed. It
  rejects repeated data/pages, changing totals, malformed metadata, and premature empty pages
  (FR-004, research.md R8).
- Completed results are inspectable only through `EvaluationRun.results`, a public read-only
  detached snapshot; `retain_results()` deep-copies into canonical private storage, while
  `results` and `delivery_payload()` each return a fresh `MappingProxyType(deepcopy(...))`. Neither
  mapping nor nested snapshot mutations can alter retained state used by later inspection/retry
  (FR-007).
- `delivery_payload()` returns exactly `(fresh_read_only_results_snapshot, retained_observer)`.
  Successful initial publication or retry clears the private observer reference; failed publication
  retains it so retry remains possible. A run-owned `complete_delivery(status)` operation applies
  the successful terminal status and clears the observer under one state lock.
- `ResultObserver` is an `ABC` with abstract
  `publish(run, results: Mapping[str, EvaluationResult]) -> None`. `start()` uses
  `isinstance(observer, ResultObserver)` and rejects a null or invalid observer before creating an
  `EvaluationRun` (FR-007).
- `Evaluator.__init__` accepts injectable `config_manager`, `metric_factory`, `collector`,
  `normalizer`, `orchestrator`, and `publisher` collaborators. Each is optional: omitted
  collaborators are composed from the production defaults, while supplied collaborators are used
  unchanged. The default `EvaluationOrchestrator` receives the selected `config_manager`; the
  default collector is built with `TraceRepository`. This is the only test seam for collaborators.
- At most one retry attempt executes per run at a time (FR-007 last clause).
- Initial publication runs under the non-final `DELIVERING` status; `wait()` remains unsignaled and
  `end_timestamp` remains unset until publication succeeds or fails. Delivery retries retain
  `DELIVERY_FAILED` while in flight so the retry lock remains the authoritative concurrent-retry
  signal (FR-007/FR-011).
- `end_timestamp` is the immutable first-terminal timestamp. A successful retry updates status but
  neither changes this timestamp nor clears/replaces the completion event (FR-009).
- Every mutation and property read of run state is guarded by a per-run `threading.RLock`.
  `EvaluationRun.snapshot()` captures status, progress, timestamps, errors, and detached results in
  one critical section for coherent multi-field observation. External collaborator calls are never
  made while holding that lock (FR-003/FR-008/FR-012).
- `EvaluationRun` enforces the transition matrix from FR-011. `total` is set once to a non-negative
  integer, processing cannot increment before that point or beyond total, and invalid mutations
  fail atomically. `wait()` accepts `float | None`: `None` waits indefinitely, non-positive numeric
  values perform an immediate check, and unsupported values propagate `threading.Event.wait()`'s
  `TypeError`.
- `Evaluator` never reads or mutates `MetricFactory` or `EvaluationRun` protected attributes;
  registry queries, run-state updates, retained-delivery access, and retry serialization all use
  public methods on the class that owns that state (Constitution Principle I).
- No raw exception/credential text reaches `PerTraceError.message`: the implementation reuses
  `sanitize_error()`, removes raw exception text and bearer/API-key/password/opaque credential
  values, and preserves a stable stage-specific fallback suitable for requester display.
- An unexpected worker-level exception always produces `UNABLE_TO_RUN`, a sanitized
  `EvaluationRun.failure_message`, an end timestamp, and completion signal.
- Failure while creating or starting the background thread is handled against the already-created
  run in the same way. Since validation already accepted the run, `start()` returns that handle in
  terminal `UNABLE_TO_RUN` rather than propagating the startup exception; it never leaves the run
  in `STARTED`.
- Per-metric failures represented inside a returned M3.1 `EvaluationResult` remain governed by the
  existing `EvaluationOrchestrator`; only a raised per-trace call becomes `evaluation_failed`.

**Scale/Scope**: Python 3.11+ compatible implementation, developed in this repository's Python 3.13
environment. One domain package addition (files, not a new top-level package —
`deepeval_platform/evaluation/` already exists): `evaluation_config.py`, `evaluation_run.py`
(`EvaluationRun`, `RunStatus`, `PerTraceError`, `PerTraceErrorCode`), `evaluator.py`,
`result_publisher.py`; one additive
parameter on the existing `EvaluationOrchestrator.evaluate()`; five new exception classes appended
to the existing `evaluation/errors.py` (`UnknownBotError`, `InvalidPeriodError`,
`InvalidRetryStateError`, `RetryInProgressError`, `DuplicateMetricError`) plus reuse of three existing ones
(`EmptyMetricListError`, `UnknownMetricError`, `InvalidThresholdError`). No new migration, no new
config schema, no new runtime dependency.

## Constitution Check

*GATE: Re-checked against constitution v2.0.0.*

| Principle | Check | Status |
|---|---|---|
| I. OOP-First | `EvaluationConfig` (passive value object), `EvaluationRun`/`RunStatus`/`PerTraceError` (run state), `ResultPublisher`/`ResultObserver` (publication), and `Evaluator` (orchestration only, delegates extraction/normalization/evaluation to their existing owners) each have one responsibility; no new monolithic file. | PASS |
| II. DeepEval-First | Official documentation and the installed DeepEval 4.0.7 API were reviewed (research.md, "DeepEval-first native capability review"). Native `evaluate()`/`AsyncConfig`/`ErrorConfig` cover completed test-case batch execution, concurrency, and evaluation-error policy, but not external trace extraction/normalization, an immediate live run handle, stage-aware progress/failures, observer publication, or delivery-only retry. `Evaluator` therefore remains a project-local lifecycle adapter and delegates all scoring to the already-native-backed M3.1 `EvaluationOrchestrator`; it does not reimplement metric measurement. | PASS |
| III. LangChain-First | Not applicable — this milestone orchestrates the evaluator's own pipeline, not a bot-under-evaluation integration (explicit scope boundary in Principle III). | N/A |
| IV. TDD | Every new class/behavior gets a test written and observed RED before its implementation; coverage stays >=80% and the final gate verifies RED-before-GREEN evidence (quickstart.md enumerates the required scenarios). Actual evidence took the form constitution v2.1.0 Gate 1(b) describes: commits landed at phase granularity rather than per-task, so ordering isn't reconstructable from `git log` alone; research.md's T057 audit note is the canonical record of live RED→GREEN verification during the session — see research.md:385-397. | PASS (process gate; evidence per Gate 1(b), not commit history — see research.md T057) |
| V. Zero Hardcode | No new credential/config value; the one config read (`bots.{bot_id}.bot_type`) goes through `ConfigManager`, the sole reader. | PASS |
| VI. Extensibility | `ResultPublisher` is injected (constructor parameter) and delivers each run only to its requester-supplied `ResultObserver`. Adding an output target requires only a new observer supplied when starting a run, with zero `Evaluator` changes, satisfying the constitution's mandatory Observer application for evaluation results. | PASS |

No design-pattern exception is requested. Constitution v2.0.0 was in force at plan time; v2.1.0
(2026-07-20) later amended Gate 1's evidence wording and the Core runtime version in response to
this feature's own research.md T056/T057 findings — see constitution.md Sync Impact Report. All
principle checks pass; no implementation blocker remains.

## Project Structure

### Documentation (this feature)

```text
specs/009-evaluator-principal/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md         # Phase 1 output (/speckit-plan command)
├── quickstart.md        # Phase 1 output (/speckit-plan command)
├── contracts/
│   └── evaluator-api.md # Phase 1 output (/speckit-plan command)
└── tasks.md              # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
deepeval_platform/
└── evaluation/
    ├── evaluation_config.py     # NEW — EvaluationConfig
    ├── evaluation_run.py        # NEW — EvaluationRun/Snapshot, RunStatus, PerTraceError/Code
    ├── result_publisher.py      # NEW — ResultPublisher and ResultObserver
    ├── evaluator.py              # NEW — Evaluator (the orchestrator)
    ├── errors.py                  # MODIFIED — UnknownBotError, InvalidPeriodError,
    │                              #   InvalidRetryStateError, RetryInProgressError,
    │                              #   DuplicateMetricError added
    ├── metrics/
    │   └── metric_factory.py       # MODIFIED — public is_registered() query added
    └── evaluation_orchestrator.py # MODIFIED — evaluate() gains optional `thresholds` param
deepeval_platform/collection/
└── trace_collector.py             # MODIFIED — per-trace extraction outcome contract
deepeval_platform/repositories/
└── trace_repository.py            # MODIFIED — exhaustive paginated date-range read
tests/
├── unit/evaluation/
│   ├── test_evaluation_config.py    # NEW
│   ├── test_evaluation_run.py        # NEW
│   ├── test_evaluator.py             # NEW
│   ├── test_evaluation_orchestrator.py  # MODIFIED — threshold-override coverage added
│   ├── test_result_publisher.py       # NEW
│   ├── test_errors.py                 # MODIFIED — new exception classes covered
│   └── metrics/
│       └── test_metric_factory.py     # MODIFIED — public registration-query coverage added
├── unit/collection/
│   └── test_trace_collector.py           # MODIFIED — partial extraction outcome coverage added
├── unit/repositories/
│   └── test_trace_repository.py          # MODIFIED — exhaustive pagination coverage added
└── integration/
    └── test_evaluator_flow_integration.py  # NEW
```

**Structure Decision**: Single project (existing `deepeval_platform/` package, no new top-level
directory). All new types are added to the existing `evaluation/` domain package alongside the
M2.1/M2.2/M3.1 collaborators they compose — consistent with the constitution's domain-organized
module layout (Principle I) and with how M4.1 added `synthetic/` as a sibling domain rather than
scattering related classes elsewhere. No `contracts/` HTTP schema is generated beyond the internal
Python API document, matching M3.1's precedent (this milestone likewise exposes no external
network interface — Assumptions explicitly defer the trigger mechanism to a separate milestone).

## Complexity Tracking

*No constitution violations — table not applicable.*

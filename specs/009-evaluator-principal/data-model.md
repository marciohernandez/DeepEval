# Phase 1 Data Model: Evaluator Principal (M4.2)

All new types live under `deepeval_platform/evaluation/`, alongside the M3.1 types they compose
(`EvaluationContext`, `EvaluationResult`/`MetricResult`, `errors.py`). Principle II applies and the
required native capability review is recorded in research.md. DeepEval 4.0.7 provides native batch
evaluation, concurrency/error configuration, and a completed-result aggregate, but no native type
implements this feature's external trace lifecycle, immediately-queryable run state, stage-aware
errors, observer delivery, or delivery-only retry. These project-local models cover only that gap;
metric scoring remains delegated to DeepEval-backed M3.1 adapters.

## `EvaluationConfig` (`evaluation/evaluation_config.py`)

| Field | Type | Notes |
|---|---|---|
| `bot_id` | `str` | Non-empty after trimming; must identify a configured bot (`bots.{bot_id}.bot_type` present); FR-002 |
| `metric_thresholds` | `list[MetricThreshold]` | ordered submitted entries; preserves duplicate names until FR-015 validation |
| `period_start` | `datetime` | Must be a datetime; naive means UTC, aware is converted to UTC; inclusive boundary |
| `period_end` | `datetime` | Must be a datetime; naive means UTC, aware is converted to UTC; exclusive and strictly later |

`MetricThreshold` is a frozen value object containing `name: str` and `threshold: float`. After
validation, `Evaluator.start()` converts the entries to an internal `dict[str, float]` for
`EvaluationOrchestrator.evaluate()`. `__post_init__` normalizes both timestamps to UTC (research.md R7) and eagerly validates the
period bound (`period_start < period_end` → `InvalidPeriodError` otherwise, per the clarification
that equal boundaries are invalid). Metric/threshold/bot validation happens in
`Evaluator.start()`, not here, because it requires collaborators (`MetricFactory`, `ConfigManager`)
that a plain dataclass should not depend on — keeping `EvaluationConfig` a passive value object
(Principle I: no monolithic files/classes; validation that needs collaborators belongs to the
orchestrator that owns those collaborators, mirroring how `TraceFilter` self-validates only what
it can check with no dependencies, while `EvaluationOrchestrator` — not `EvaluationContext` —
validates metric names against `MetricFactory`).

The `float` annotation defines the supported API type but construction does not coerce runtime
input, so invalid raw values remain detectable at the all-or-nothing `Evaluator.start()` boundary.
Validation accepts only `int`/`float` values excluding `bool`, requires `math.isfinite()`, and then
checks the inclusive range. A valid integer is converted to float only when the internal mapping is
built. `metric_thresholds` accepts only actual `MetricThreshold` instances. Mappings, tuples,
arbitrary objects with similarly named attributes, and malformed constructor calls are rejected
rather than interpreted through duck typing.

**Rejection conditions, evaluated in `Evaluator.start()` before any `EvaluationRun` is created**
(FR-002/FR-014/FR-015, all-or-nothing — first violation found aborts before run state exists):

| Condition | Exception (from `evaluation/errors.py`) |
|---|---|
| `metric_thresholds == []` | `EmptyMetricListError` (reused from M3.1 — same "at least one metric" rule) |
| duplicate entry name | `DuplicateMetricError` (new; FR-015) |
| any entry for which `MetricFactory.is_registered(name)` is false | `UnknownMetricError` (reused from M3.1) |
| any entry threshold is a `bool`, is not `int`/`float`, is non-finite, or is outside `[0.0, 1.0]` | `InvalidThresholdError` (reused from M3.1; no string coercion) |
| exact `bots.{bot_id}.bot_type` key explicitly reported missing, or returned empty | `UnknownBotError` (new, research.md R4) |
| `period_end` not strictly later than `period_start` | `InvalidPeriodError` (new; raised earlier, in `__post_init__`, since it needs no collaborator) |
| either period boundary is not a `datetime` | `TypeError` (raised in `__post_init__`) |
| `bot_id` or any metric name is empty/whitespace-only | `ValueError` before run creation |

Only an explicit missing-key signal from `ConfigManager` for the exact bot key, or an empty lookup
result, is translated to `UnknownBotError`. Configuration-loading, parsing, and other `ConfigError`
failures are not user-input validation errors; they propagate without an `EvaluationRun` being
created.

## `RunStatus` (`evaluation/evaluation_run.py`)

```python
class RunStatus(str, Enum):
    STARTED = "started"                              # accepted; extraction in flight
    IN_PROGRESS = "in_progress"                       # extraction done; total known; evaluating traces
    DELIVERING = "delivering"                         # evaluation done; initial observer call in flight
    COMPLETED = "completed"                           # all traces processed, zero PerTraceError, results published
    COMPLETED_WITH_FAILURES = "completed_with_failures"  # >=1 PerTraceError, results published
    UNABLE_TO_RUN = "unable_to_run"                   # setup or non-trace worker failure prevents completion
    DELIVERY_FAILED = "delivery_failed"               # evaluation finished; publication raised
```

Same `(str, Enum)` convention as `BotType`/`InteractionStatus`. `STARTED`, `IN_PROGRESS`, and
`DELIVERING` are non-terminal lifecycle states. Terminal states:
`COMPLETED`, `COMPLETED_WITH_FAILURES`, `UNABLE_TO_RUN`, `DELIVERY_FAILED` — FR-011 requires all
four to be distinguishable.

## `PerTraceErrorCode` and `PerTraceError` (`evaluation/evaluation_run.py`)

```python
class PerTraceErrorCode(str, Enum):
    EXTRACTION_FAILED = "extraction_failed"
    NORMALIZATION_FAILED = "normalization_failed"
    EVALUATION_FAILED = "evaluation_failed"
```

The code is selected from the failed pipeline stage, never from an implementation-specific
exception class. This keeps the public error contract stable when collaborators change their
internal exception types.

| Field | Type | Notes |
|---|---|---|
| `trace_id` | `str` | The affected `TraceRecord.trace_id` |
| `stage` | `Literal["extraction", "normalization", "evaluation"]` | FR-010; see research.md R5 for reachability of `"extraction"` in this milestone |
| `error_code` | `PerTraceErrorCode` | `EXTRACTION_FAILED`, `NORMALIZATION_FAILED`, or `EVALUATION_FAILED`, matching `stage` |
| `message` | `str` | Stable stage-specific fallback sanitized by `sanitize_error()`; no raw exception text or bearer/API-key/password/opaque credential value |

## `TraceCollectionResult` (`collection/trace_collector.py`)

| Field | Type | Notes |
|---|---|---|
| `traces` | `list[TraceRecord]` | Every successfully extracted trace in the requested half-open period; the exhaustive evaluation path has no 500-trace cap |
| `errors` | `list[TraceCollectionError]` | Identified trace-specific extraction failures; each includes `trace_id`, stable error code, and sanitized message |

`TraceCollectionResult` rejects any successful/error outcome with an empty or whitespace-only
`trace_id`; exhaustive collection then fails as a whole because no stable requester-correlatable
identity can be invented. For valid IDs it enforces one outcome per `trace_id` across both collections. A
duplicate ID is represented by exactly one `TraceCollectionError`; no `TraceRecord` with that ID
remains in `traces`, and no second error for that ID remains in `errors`. Its constructor rejects an
invalid result that violates this invariant, protecting the Evaluator even when tests or alternate
collectors construct the value directly.

`TraceCollector.collect_all()` returns `TraceCollectionResult`. It uses
`TraceRepository.get_all_by_date_range()` to exhaust every response page and rechecks
`period_start <= trace.start_time < period_end` locally. It raises only when collection setup,
connectivity, or retrieval fails before an affected trace can be identified. `Evaluator` converts
each `TraceCollectionError` into `PerTraceError(stage="extraction",
error_code=EXTRACTION_FAILED)` and continues processing `traces`. M2.1's existing `collect()` method
continues to return at most the most recent 500 traces for its existing callers.
The repository operation uses one fixed page size and a stable deterministic ordering for every
page in a request. It raises `TraceRepositoryError` for malformed/changing pagination metadata,
repeated pages or records, or a premature empty page, preventing loops and partial success.

## `EvaluationRun` (`evaluation/evaluation_run.py`)

| Field | Type | Notes |
|---|---|---|
| `id` | `UUID` | `uuid4()`, assigned at creation (FR-003); globally unique, opaque |
| `status` | `RunStatus` | Synchronized read-only property backed by `_status`; see State Transitions below |
| `processed` | `int` | Synchronized read-only property backed by `_processed`; starts at 0 |
| `total` | `int \| None` | Synchronized read-only property backed by `_total`; `None` until extraction completes, then fixed |
| `start_timestamp` | `datetime` | Synchronized read-only property; set at creation, UTC |
| `end_timestamp` | `datetime \| None` | First-terminal timestamp. Set once on the first terminal status; a later successful retry does not move it. |
| `errors` | `tuple[PerTraceError, ...]` | Synchronized detached snapshot of private `_errors`; empty means clean run |
| `failure_message` | `str \| None` | Synchronized read-only sanitized diagnostic for a whole-run failure |
| `results` | `Mapping[str, EvaluationResult]` | Fresh `MappingProxyType(deepcopy(_results))` for inspection. Empty until results are assembled; remains available after delivery failure and retries while the handle is reachable. |
| `_results` | `dict[str, EvaluationResult]` | Private canonical deep copy; trace_id → per-trace `EvaluationResult` (M3.1 type), retained for publication/retry as long as this object is reachable (research.md R6) |
| `_observer` | `ResultObserver` | Private; supplied to `Evaluator.start()` by the requester and retained only to deliver this run's results or retry its failed delivery |
| `_state_lock` | `threading.RLock` | Private; guards every mutable backing field and coherent snapshot construction; never held during collaborator calls |
| `_retry_lock` | `threading.Lock` | Private; excluded from `repr`/equality; serializes `retry_delivery` (FR-007 last clause) |
| `_completion_event` | `threading.Event` | Private; set exactly once when the run first reaches a terminal status; never cleared by delivery retry |

All mutable backing fields remain encapsulated by `EvaluationRun`. `Evaluator` uses public
behavior methods to update and inspect run state: `set_total(total)`, `increment_processed()`,
`append_error(error)`, `set_failure_message(message)`, `retain_results(results)`,
`delivery_payload()`, `transition_to(status)`, `complete_delivery(status)`, `snapshot()`,
`begin_retry()`, `end_retry()`, and `release_observer()`. These methods
own the relevant invariants (including first-terminal timestamp/event signaling and non-blocking
per-run retry serialization); collaborators do not access underscore-prefixed fields directly.
`retain_results()` deep-copies its input into `_results`. `results` builds a new
`MappingProxyType(deepcopy(_results))`; `delivery_payload()` returns exactly that fresh detached
snapshot together with the retained observer as `(results_snapshot, observer)`. They never expose
`_results` or reuse a snapshot previously supplied to an observer. `release_observer()` clears the
private reference after successful initial delivery or retry; failed delivery retains it.
`complete_delivery(status)` validates a completion status, applies it, records first-terminal
state, signals completion if needed, and clears the observer in one `_state_lock` critical section.

Every public property and behavior method acquires `_state_lock`. `begin_retry()` atomically checks
for `DELIVERY_FAILED` and tries `_retry_lock` while holding `_state_lock`, raising
`InvalidRetryStateError` or `RetryInProgressError` as appropriate. External calls are made only
after `_state_lock` is released. A successful retry records its completion status while the retry
guard is still held, then `end_retry()` releases that guard.

`progress` is a derived read (not a stored field, so it can never drift from `processed`/`total`):
`None` while `total is None`; otherwise `1.0` for a zero-trace run (`total == 0`, per FR-008's
explicit "treated as complete rather than requiring division by zero"), else
`processed / total`.

## `EvaluationRunSnapshot`

`EvaluationRunSnapshot` is a frozen dataclass returned by `EvaluationRun.snapshot()`. The method
constructs all fields in one `_state_lock` critical section:

| Field | Type |
|---|---|
| `id` | `UUID` |
| `status` | `RunStatus` |
| `processed` | `int` |
| `total` | `int \| None` |
| `progress` | `float \| None` |
| `start_timestamp` | `datetime` |
| `end_timestamp` | `datetime \| None` |
| `errors` | `tuple[PerTraceError, ...]` (deeply detached) |
| `failure_message` | `str \| None` |
| `results` | `Mapping[str, EvaluationResult]` (deeply detached and read-only) |

After collection succeeds, `total` is the count of successfully collected traces plus identified
trace-specific collection errors. Converting each collection error to an extraction-stage
`PerTraceError` increments `processed` once, just as successful, normalization-failed, and
evaluation-failed traces do. Thus, every terminal run after successful collection has
`processed == total`.

`wait(timeout: float | None = None) -> bool` is the public synchronization operation. It blocks
until `_completion_event` is set or the optional timeout expires, returning `True` only when the
run has reached its first terminal status. This provides deterministic completion observation for
callers and tests without changing `Evaluator.start()`'s asynchronous behavior.
Its timeout semantics intentionally match `threading.Event.wait()`: `None` waits indefinitely and
a non-positive numeric timeout performs an immediate check. Unsupported timeout types propagate
the standard library's `TypeError`.

### State transitions

```
                 (validation fails)
  [no run created] ─────────────────────────────────► (nothing — caller gets an exception)

  start() validation passes
         │
         ▼
     STARTED  ──(extraction/setup raises)──────────────► UNABLE_TO_RUN [terminal]
         │
         │ (extraction succeeds; total becomes known)
         ▼
   IN_PROGRESS ──(each trace: normalize+evaluate,
          │         isolated failures appended to errors,
          │         processed incremented either way)
          │
          └──(unexpected non-trace worker failure)────► UNABLE_TO_RUN [terminal]
         │
         │ (all traces processed)
         ▼
     DELIVERING [non-terminal; wait() remains unsignaled]
         │
         ▼
     results_snapshot, observer = run.delivery_payload()
     publisher.publish(run, results_snapshot, observer)
         │
    ┌────┴────┐
 success      raises
    │            │
    ▼            ▼
COMPLETED /   DELIVERY_FAILED [terminal]
COMPLETED_        │
WITH_FAILURES     │ retry_delivery(run) — only if status is DELIVERY_FAILED
[terminal]        │ and no retry already in flight
                   ▼
               results_snapshot, observer = run.delivery_payload()
               publisher.publish(run, results_snapshot, observer) again
                   │
              ┌────┴────┐
           success      raises
              │            │
              ▼            ▼
        COMPLETED /   stays DELIVERY_FAILED
        COMPLETED_
        WITH_FAILURES
        (per original
         trace outcome)
        [terminal]
```

`COMPLETED` vs. `COMPLETED_WITH_FAILURES` is decided once, from `len(run.errors) == 0`, at the
moment trace processing finishes — both the first delivery attempt and any later successful retry
apply that same, already-fixed outcome (FR-011's "restore the ... outcome that corresponds to the
run's trace-evaluation results").

The initial observer sees `run.status == DELIVERING`. This state does not set `end_timestamp` or
`_completion_event`. A delivery retry is invoked from the already-terminal `DELIVERY_FAILED` state
and deliberately retains that status while its retry guard is held; it does not transition back to
`DELIVERING`.

Every transition into `UNABLE_TO_RUN`, `COMPLETED`, `COMPLETED_WITH_FAILURES`, or
`DELIVERY_FAILED` sets `_completion_event` after recording the terminal status and first
`end_timestamp`. A successful delivery retry changes a delivery-failed status to its original
completion outcome but does not alter the timestamp or clear the already-set event.

The worker entrypoint catches unexpected `Exception` instances that escape its planned
setup/extraction/trace/publication handling. It sanitizes the exception into `failure_message`,
then uses `run.transition_to(UNABLE_TO_RUN)`. Trace-specific failures remain
`PerTraceError` entries and are never reclassified as a whole-run failure.
The same protected entrypoint covers failure to start the background worker after run creation.
Whole-run diagnostics use `sanitize_error()` with a stable fallback and never expose raw exception
text or credential material.

## `ResultPublisher` and `ResultObserver` (`evaluation/result_publisher.py`)

`ResultPublisher` is the mandatory Observer-pattern subject for evaluation outputs. The requester
supplies one `ResultObserver` to `Evaluator.start()`, which stores it privately on the resulting
run. Once trace evaluation is complete, `ResultPublisher` notifies only that observer while the run
is in non-final `DELIVERING`; the callback outcome then determines the final status. This milestone
defines these interfaces only; durable observer implementations remain out of scope.

```python
class ResultObserver(ABC):
    @abstractmethod
    def publish(self, run: EvaluationRun, results: Mapping[str, EvaluationResult]) -> None:
        """Receive completed results. Raise on delivery failure."""
```

class ResultPublisher:
    def publish(
        self,
        run: EvaluationRun,
        results: Mapping[str, EvaluationResult],
        observer: ResultObserver,
    ) -> None:
        """Notify this run's observer; propagate a publication failure to Evaluator."""

No concrete production observer ships in this milestone (research.md R6) — durable persistence
(`EvaluationRepository`) and downstream destination observers are separately specified future
capabilities per the spec's Assumptions.

`Evaluator.start()` requires one non-null `ResultObserver`; a null or invalid observer is rejected
before an `EvaluationRun` is created.

## `Evaluator` (`evaluation/evaluator.py`)

The orchestrator (spec's Key Entity). Composes, does not reimplement:

| Collaborator | Role | Reused from |
|---|---|---|
| `ConfigManager` | bot-existence check (R4) | M1 |
| `TraceCollector` | extraction (bulk, per bot/period) | M2.1 |
| `TraceNormalizer` | per-trace normalization | M2.2 |
| `EvaluationOrchestrator` | per-trace metric evaluation, given override thresholds (R3) | M3.1 |
| `ResultPublisher` | publication of completed results to observers | this milestone (interface only) |

Public surface — see `contracts/evaluator-api.md`.

`Evaluator.__init__` accepts optional `config_manager`, `metric_factory`, `collector`,
`normalizer`, `orchestrator`, and `publisher` collaborators. Production callers may omit all of
them; the evaluator then composes `ConfigManager.instance()`, `MetricFactory`,
`TraceCollector(TraceRepository())`, `TraceNormalizer()`, an `EvaluationOrchestrator` configured
with that same config manager, and `ResultPublisher`. Tests supply fakes through these arguments;
the evaluator does not patch globals or inspect collaborator internals.

## Key entity cross-reference (spec → implementation)

| Spec Key Entity | Type | File |
|---|---|---|
| `EvaluationConfig` | `EvaluationConfig` (dataclass) | `evaluation/evaluation_config.py` |
| `EvaluationRun` | `EvaluationRun` (dataclass) + `RunStatus` (enum) | `evaluation/evaluation_run.py` |
| `EvaluationRunSnapshot` | `EvaluationRunSnapshot` (frozen dataclass) | `evaluation/evaluation_run.py` |
| `PerTraceError` | `PerTraceError` (dataclass) | `evaluation/evaluation_run.py` |
| `Evaluator` | `Evaluator` (class) | `evaluation/evaluator.py` |

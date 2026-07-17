# Contract: Evaluator API Surface (internal Python API — no external network interface)

Like `contracts/evaluation-api.md` (M3.1), this milestone has no HTTP/CLI surface of its own —
triggering a run (manual call, scheduler, or a future API endpoint) is explicitly out of scope
(spec Assumptions). The "contract" here is the Python API `Evaluator` exposes to whatever triggers
it and to tests.

## `EvaluationConfig`

```python
from datetime import datetime, timezone
from deepeval_platform.evaluation.evaluation_config import EvaluationConfig, MetricThreshold

config = EvaluationConfig(
    bot_id="test_rag_bot",
    metric_thresholds=[
        MetricThreshold("faithfulness", 0.85),
        MetricThreshold("answer_relevancy", 0.7),
    ],
    period_start=datetime(2026, 7, 1, tzinfo=timezone.utc),
    period_end=datetime(2026, 7, 8, tzinfo=timezone.utc),
)

EvaluationConfig(
    bot_id="test_rag_bot",
    metric_thresholds=[MetricThreshold("faithfulness", 0.85)],
    period_start=datetime(2026, 7, 8),
    period_end=datetime(2026, 7, 1),
)
# -> InvalidPeriodError, raised eagerly in __post_init__ (needs no collaborator)
```

- Naive `datetime` values are treated as UTC; aware values are converted to UTC. Both boundaries
  are always UTC after construction. Non-`datetime` boundaries raise `TypeError` during
  construction.
- An empty entry list, duplicate names, and threshold-domain/unknown-metric checks are **not**
  enforced here — they require centralized validation and `MetricFactory`/`ConfigManager`, and are
  enforced by `Evaluator.start()`
  (below). The entry list preserves duplicate submissions so they can be rejected.

## `Evaluator` — the primary entry point for this feature

```python
from deepeval_platform.evaluation.evaluator import Evaluator
from deepeval_platform.evaluation.result_publisher import ResultObserver

evaluator = Evaluator()  # composes production ConfigManager, MetricFactory, TraceCollector,
                          # TraceNormalizer, EvaluationOrchestrator, and ResultPublisher
observer = InMemoryResultObserver()

run = evaluator.start(config, observer)  # -> EvaluationRun, returned immediately (FR-003)
run.status                      # RunStatus.STARTED, IN_PROGRESS, DELIVERING, or terminal —
                                 # a background thread is already mutating this same object
run.processed                   # int, starts at 0
run.total                       # int | None — None until extraction completes
run.progress                    # float | None — derived; None while run.total is None
state = run.snapshot()          # frozen EvaluationRunSnapshot — coherent multi-field read
run.wait(timeout=5.0)            # bool — True when a first terminal status is reached in 5 seconds
```

`Evaluator.__init__` accepts optional `config_manager`, `metric_factory`, `collector`,
`normalizer`, `orchestrator`, and `publisher` keyword arguments. Omitted collaborators use the
production composition shown above; supplied collaborators are used unchanged. The default
`EvaluationOrchestrator` receives the selected config manager, and the default collector is
constructed with `TraceRepository`. Tests must provide fakes through this constructor rather than
patching global collaborators.

`observer` is exactly one `ResultObserver` supplied by the requester. It receives results for
this run only and is retained privately on `run` solely so `retry_delivery(run)` can retry the
same failed delivery. It is not a global subscriber and is never exposed through public run state.
During the initial observer callback, the supplied `run` has status `DELIVERING`.
The `results` argument is a fresh detached `Mapping[str, EvaluationResult]` snapshot. Its mapping
cannot be modified, and mutating a nested object from that snapshot cannot change `run.results` or
any later retry payload.

`run.wait(timeout=None)` blocks until the run first reaches `UNABLE_TO_RUN`, `COMPLETED`,
`COMPLETED_WITH_FAILURES`, or `DELIVERY_FAILED`. It returns `True` when that happens before the
optional timeout and `False` on timeout. A later successful delivery retry does not clear this
completion signal.
`None` waits indefinitely; zero or a negative numeric timeout performs an immediate check, matching
`threading.Event.wait()`. Unsupported timeout types raise the standard library `TypeError`.

The returned handle is the only run-retrieval mechanism in this milestone. There is no global run
registry or `get_run(id)` API; durable lookup is deferred with persistence.

Each individual state property acquires the run's state lock. Callers that need multiple fields
from one instant use `run.snapshot()` rather than composing separate property reads. The frozen
snapshot contains `id`, `status`, `processed`, `total`, `progress`, timestamps, detached errors,
failure message, and detached read-only results.

**Pre-conditions enforced before any `EvaluationRun` is created** (all raise, no partial state,
mirrors `contracts/evaluation-api.md`'s pre-condition table):

| Condition | Exception |
|---|---|
| `metric_thresholds == []` | `EmptyMetricListError` |
| duplicate metric entry name | `DuplicateMetricError` |
| any metric name unregistered in `MetricFactory` | `UnknownMetricError` |
| any threshold is boolean, non-`int`/`float`, non-finite, or outside `0.0–1.0` | `InvalidThresholdError` |
| exact `bots.{bot_id}.bot_type` key explicitly reported missing, or returned empty | `UnknownBotError` |
| `bot_id` or any metric name is empty/whitespace-only | `ValueError` |
| either period boundary is not a `datetime` | `TypeError` |
| `period_end` not strictly later than `period_start` | `InvalidPeriodError` (raised by `EvaluationConfig` itself, before `start()` is even reached) |
| `observer` is null or not a `ResultObserver` | `TypeError` |

Threshold validation performs no string coercion: `0`, `1`, `0.5`, and their finite in-range
integer/float equivalents are accepted; `True`, `False`, `"0.5"`, `NaN`, and either infinity are
rejected before run creation. Accepted values are normalized to float only after all entries pass.
Only `ConfigManager`'s explicit missing-key outcome for the exact bot-key lookup, or an empty
returned value, is translated to `UnknownBotError`. Configuration-loading, parsing, and other
`ConfigError` failures propagate without creating a run.

**Post-`start()` behavior** (all asynchronous, on the same returned `run` object):

- Extraction setup (`TraceCollector.collect_all`) raises before it can identify a trace →
  `run.status = UNABLE_TO_RUN`, `run.end_timestamp` set, `run.total` stays `None`, and
  `run.failure_message` contains a sanitized diagnostic.
  (Edge case: trace source unreachable.)
- `TraceCollector.collect_all()` exhausts every repository page without the M2.1 500-trace cap and
  returns successful traces and identified trace-specific extraction
  errors. The Evaluator records each collection error as
  `PerTraceError(stage="extraction", error_code=EXTRACTION_FAILED)` and includes both successes
  and failures in the final total/progress counts. `run.total` is their combined count, and each
  collection error increments `run.processed` once.
- Collection produces exactly one outcome per non-empty `trace_id`. If an ID is duplicated across
  collected records/outcomes, it contributes one extraction error and no successful trace/result;
  unique IDs continue normally. Consequently, assigning results by trace ID cannot overwrite a
  prior result.
- An empty or whitespace-only trace ID invalidates exhaustive collection and yields
  `UNABLE_TO_RUN`; the collector never invents a replacement ID.
- Extraction succeeds with zero traces and no collection errors → `run.total = 0`; the observer is
  called exactly once with an empty detached read-only mapping, and the run reaches completion only
  after that publication succeeds. A zero-trace period is not an error (SC-004).
- Extraction succeeds with N traces → `run.total = N`, `run.status = IN_PROGRESS`; each trace is
  normalized then evaluated. A per-trace failure appends a `PerTraceError` to `run.errors` and
  still increments `run.processed` — it never stops the remaining traces (FR-010, SC-002).
- A trace-specific extraction failure is recorded with `stage == "extraction"`; processing
  continues for every successfully discovered trace and the run ends with failures.
- Per-trace errors use only the stable stage-matched codes `extraction_failed`,
  `normalization_failed`, and `evaluation_failed`; the underlying exception class name is never
  exposed as an error code.
- A returned `EvaluationResult` may contain metric-level error details according to the existing
  `EvaluationOrchestrator` contract and still counts as a successful trace evaluation. Only an
  exception raised by the orchestrator call creates a trace-level `evaluation_failed` error.
- An unexpected worker-level error that cannot be associated with an identified trace transitions
  the run to `UNABLE_TO_RUN`, records a sanitized `run.failure_message`, and signals `run.wait()`;
  it never leaves the run in `STARTED`, `IN_PROGRESS`, or `DELIVERING`.
- Once every trace is processed and results are retained, `Evaluator` transitions the run to
  non-terminal `DELIVERING`, without setting `end_timestamp` or signaling `run.wait()`, then calls
  `results, observer = run.delivery_payload()` and then invokes the injected
  `ResultPublisher.publish(run, results, observer)` for this run's supplied observer
  only. The observer sees `run.status == DELIVERING`:
  - succeeds → one run-owned synchronized operation sets `COMPLETED` if `run.errors` is empty, else
    `COMPLETED_WITH_FAILURES`, records terminal state, and releases the private observer reference.
  - raises → `run.status = DELIVERY_FAILED`; `run.end_timestamp` set; completed results remain
    available through `run.results`.

## Retry

```python
retried = evaluator.retry_delivery(run)   # takes the SAME EvaluationRun object, not an id
```

- Blocking call — makes exactly one new `ResultPublisher.publish(...)` attempt using the results
  and observer already retained on `run`; **never** re-extracts, re-normalizes, or re-evaluates
  (SC-007).
- Each attempt receives a new detached read-only snapshot built from the run's canonical retained
  copy; snapshots from prior failed attempts are never reused.
- `run.begin_retry()` atomically validates `DELIVERY_FAILED` and acquires the retry guard under the
  state lock. Any other status raises `InvalidRetryStateError`; an in-flight retry raises
  `RetryInProgressError` (at most one retry attempt executes per run at a time).
- The per-run retry lock is released after every completed publication attempt, including a failed
  attempt, so a subsequent valid retry remains possible.
- On success, `run.status` becomes `COMPLETED` or `COMPLETED_WITH_FAILURES` — whichever the
  original trace-evaluation outcome was (`len(run.errors) == 0`), never re-derived from a second
  evaluation pass. On failure, `run.status` remains `DELIVERY_FAILED` and may be retried again.
  The status remains `DELIVERY_FAILED` during the retry observer call; retries do not re-enter
  `DELIVERING`. A successful retry releases the private observer reference. `end_timestamp` remains
  the timestamp of the first terminal transition (`DELIVERY_FAILED`) and is not a retry timestamp.

## Post-conditions (feature-level)

- `run.id` is a fresh `uuid4()` for every `start()` call — concurrent runs for the same or
  different bots never collide and never share mutable state (FR-012).
- Every trace ID appears at most once in `run.results`; duplicate source IDs are surfaced as one
  extraction error rather than silently overwritten.
- `run.status` always ends in exactly one of `UNABLE_TO_RUN`, `COMPLETED`,
  `COMPLETED_WITH_FAILURES`, `DELIVERY_FAILED` (FR-011) — never silently stuck in `STARTED`/
  `IN_PROGRESS`/`DELIVERING` once the background thread finishes running.
- `run.wait(timeout)` deterministically reports that first terminal transition, so callers do not
  need to sleep or poll repeatedly before inspecting final state.
- Every mutable run-state transition and property read is synchronized. `run.snapshot()` never
  combines fields from different transitions, and no collector/normalizer/orchestrator/observer
  call executes while the state lock is held.
- No raw exception message, credential, or payload ever appears in a `PerTraceError.message`
  (reuses the existing `sanitize_error()` redaction — same guarantee `contracts/evaluation-api.md`
  already makes for `ErrorDetail.message`).
- `run.failure_message`, when present, is sanitized by the same redaction mechanism and is used
  only for whole-run failures, not trace-specific errors. It never contains raw exception text,
  bearer tokens, API keys, passwords, or opaque credential values and retains a stable fallback.
- `run.results` returns a fresh detached read-only mapping snapshot of completed results for
  inspection. It remains available after a delivery failure without exposing or aliasing mutable
  internal run state, including through nested result objects.

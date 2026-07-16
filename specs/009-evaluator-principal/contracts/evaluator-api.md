# Contract: Evaluator API Surface (internal Python API — no external network interface)

Like `contracts/evaluation-api.md` (M3.1), this milestone has no HTTP/CLI surface of its own —
triggering a run (manual call, scheduler, or a future API endpoint) is explicitly out of scope
(spec Assumptions). The "contract" here is the Python API `Evaluator` exposes to whatever triggers
it and to tests.

## `EvaluationConfig`

```python
from datetime import datetime, timezone
from deepeval_platform.evaluation.evaluation_config import EvaluationConfig

config = EvaluationConfig(
    bot_id="test_rag_bot",
    metric_thresholds={"faithfulness": 0.85, "answer_relevancy": 0.7},
    period_start=datetime(2026, 7, 1, tzinfo=timezone.utc),
    period_end=datetime(2026, 7, 8, tzinfo=timezone.utc),
)

EvaluationConfig(
    bot_id="test_rag_bot",
    metric_thresholds={"faithfulness": 0.85},
    period_start=datetime(2026, 7, 8),
    period_end=datetime(2026, 7, 1),
)
# -> InvalidPeriodError, raised eagerly in __post_init__ (needs no collaborator)
```

- Naive `datetime` values are treated as UTC; aware values are converted to UTC. Both boundaries
  are always UTC after construction.
- `metric_thresholds == {}` and out-of-range/unknown-metric checks are **not** enforced here —
  they require `MetricFactory`/`ConfigManager` and are enforced by `Evaluator.start()` (below).

## `Evaluator` — the primary entry point for this feature

```python
from deepeval_platform.evaluation.evaluator import Evaluator

evaluator = Evaluator()  # wires ConfigManager, TraceCollector, TraceNormalizer,
                          # EvaluationOrchestrator, and a caller-supplied ResultHandoff

run = evaluator.start(config)   # -> EvaluationRun, returned immediately (FR-003)
run.status                      # RunStatus.STARTED or already RunStatus.IN_PROGRESS/terminal —
                                 # a background thread is already mutating this same object
run.processed                   # int, starts at 0
run.total                       # int | None — None until extraction completes
run.progress                    # float | None — derived; None while run.total is None
```

**Pre-conditions enforced before any `EvaluationRun` is created** (all raise, no partial state,
mirrors `contracts/evaluation-api.md`'s pre-condition table):

| Condition | Exception |
|---|---|
| `metric_thresholds == {}` | `EmptyMetricListError` |
| any metric name unregistered in `MetricFactory` | `UnknownMetricError` |
| any threshold outside `0.0–1.0` | `InvalidThresholdError` |
| `bot_id` not configured (`bots.{bot_id}.bot_type` missing) | `UnknownBotError` |
| `period_end` not strictly later than `period_start` | `InvalidPeriodError` (raised by `EvaluationConfig` itself, before `start()` is even reached) |

**Post-`start()` behavior** (all asynchronous, on the same returned `run` object):

- Extraction (`TraceCollector.collect`) raises → `run.status = UNABLE_TO_RUN`,
  `run.end_timestamp` set, `run.total` stays `None`. (Edge case: trace source unreachable.)
- Extraction succeeds with zero traces → `run.total = 0`, `run.status` proceeds straight through
  to a completed handoff — a zero-trace period is not an error (SC-004).
- Extraction succeeds with N traces → `run.total = N`, `run.status = IN_PROGRESS`; each trace is
  normalized then evaluated. A per-trace failure appends a `PerTraceError` to `run.errors` and
  still increments `run.processed` — it never stops the remaining traces (FR-010, SC-002).
- Once every trace is processed, `Evaluator` calls the injected `ResultHandoff.deliver(run,
  results)`:
  - succeeds → `run.status = COMPLETED` if `run.errors` is empty, else
    `COMPLETED_WITH_FAILURES`; `run.end_timestamp` set.
  - raises → `run.status = DELIVERY_FAILED`; `run.end_timestamp` set; `run._results` retained.

## Retry

```python
retried = evaluator.retry_delivery(run)   # takes the SAME EvaluationRun object, not an id
```

- Blocking call — makes exactly one new `ResultHandoff.deliver(...)` attempt using the results
  already retained on `run`; **never** re-extracts, re-normalizes, or re-evaluates (SC-007).
- Requires `run.status is RunStatus.DELIVERY_FAILED`; any other status →
  `InvalidRetryStateError`, `run` unchanged.
- A concurrent retry already in flight for the same `run` → `RetryInProgressError`, `run`
  unchanged (at most one retry attempt executes per run at a time).
- On success, `run.status` becomes `COMPLETED` or `COMPLETED_WITH_FAILURES` — whichever the
  original trace-evaluation outcome was (`len(run.errors) == 0`), never re-derived from a second
  evaluation pass. On failure, `run.status` remains `DELIVERY_FAILED` and may be retried again.

## Post-conditions (feature-level)

- `run.id` is a fresh `uuid4()` for every `start()` call — concurrent runs for the same or
  different bots never collide and never share mutable state (FR-012).
- `run.status` always ends in exactly one of `UNABLE_TO_RUN`, `COMPLETED`,
  `COMPLETED_WITH_FAILURES`, `DELIVERY_FAILED` (FR-011) — never silently stuck in `STARTED`/
  `IN_PROGRESS` once the background thread finishes running.
- No raw exception message, credential, or payload ever appears in a `PerTraceError.message`
  (reuses the existing `sanitize_error()` redaction — same guarantee `contracts/evaluation-api.md`
  already makes for `ErrorDetail.message`).

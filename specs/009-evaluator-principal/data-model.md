# Phase 1 Data Model: Evaluator Principal (M4.2)

All new types live under `deepeval_platform/evaluation/`, alongside the M3.1 types they compose
(`EvaluationContext`, `EvaluationResult`/`MetricResult`, `errors.py`). None of these are DeepEval
native types (Principle II does not apply — they are this project's own orchestration models, like
`EvaluationStrategyBase`/`BotType`).

## `EvaluationConfig` (`evaluation/evaluation_config.py`)

| Field | Type | Notes |
|---|---|---|
| `bot_id` | `str` | Must identify a configured bot (`bots.{bot_id}.bot_type` present); FR-002 |
| `metric_thresholds` | `dict[str, float]` | metric name → threshold; see research.md R1 for why this single field structurally satisfies FR-015 |
| `period_start` | `datetime` | Normalized to UTC in `__post_init__`; inclusive boundary |
| `period_end` | `datetime` | Normalized to UTC in `__post_init__`; exclusive boundary, strictly later than `period_start` |

`__post_init__` normalizes both timestamps to UTC (research.md R7) and eagerly validates the
period bound (`period_start < period_end` → `InvalidPeriodError` otherwise, per the clarification
that equal boundaries are invalid). Metric/threshold/bot validation happens in
`Evaluator.start()`, not here, because it requires collaborators (`MetricFactory`, `ConfigManager`)
that a plain dataclass should not depend on — keeping `EvaluationConfig` a passive value object
(Principle I: no monolithic files/classes; validation that needs collaborators belongs to the
orchestrator that owns those collaborators, mirroring how `TraceFilter` self-validates only what
it can check with no dependencies, while `EvaluationOrchestrator` — not `EvaluationContext` —
validates metric names against `MetricFactory`).

**Rejection conditions, evaluated in `Evaluator.start()` before any `EvaluationRun` is created**
(FR-002/FR-014/FR-015, all-or-nothing — first violation found aborts before run state exists):

| Condition | Exception (from `evaluation/errors.py`) |
|---|---|
| `metric_thresholds == {}` | `EmptyMetricListError` (reused from M3.1 — same "at least one metric" rule) |
| any key not in `MetricFactory._registry` | `UnknownMetricError` (reused from M3.1) |
| any value outside `[0.0, 1.0]` | `InvalidThresholdError` (reused from M3.1) |
| `bot_id` not configured | `UnknownBotError` (new, research.md R4) |
| `period_end` not strictly later than `period_start` | `InvalidPeriodError` (new; raised earlier, in `__post_init__`, since it needs no collaborator) |

## `RunStatus` (`evaluation/evaluation_run.py`)

```python
class RunStatus(str, Enum):
    STARTED = "started"                              # accepted; extraction in flight
    IN_PROGRESS = "in_progress"                       # extraction done; total known; evaluating traces
    COMPLETED = "completed"                           # all traces processed, zero PerTraceError, handoff delivered
    COMPLETED_WITH_FAILURES = "completed_with_failures"  # >=1 PerTraceError, handoff delivered
    UNABLE_TO_RUN = "unable_to_run"                   # setup/extraction failure before processing began
    DELIVERY_FAILED = "delivery_failed"               # evaluation finished; handoff raised
```

Same `(str, Enum)` convention as `BotType`/`InteractionStatus`. Terminal states:
`COMPLETED`, `COMPLETED_WITH_FAILURES`, `UNABLE_TO_RUN`, `DELIVERY_FAILED` — FR-011 requires all
four to be distinguishable.

## `PerTraceError` (`evaluation/evaluation_run.py`)

| Field | Type | Notes |
|---|---|---|
| `trace_id` | `str` | The affected `TraceRecord.trace_id` |
| `stage` | `Literal["extraction", "normalization", "evaluation"]` | FR-010; see research.md R5 for reachability of `"extraction"` in this milestone |
| `error_code` | `str` | Stable — `type(exc).__name__` |
| `message` | `str` | Human-readable, sanitized via the existing `sanitize_error()` helper |

## `EvaluationRun` (`evaluation/evaluation_run.py`)

| Field | Type | Notes |
|---|---|---|
| `id` | `UUID` | `uuid4()`, assigned at creation (FR-003); globally unique, opaque |
| `status` | `RunStatus` | Mutated in place by the background thread; see State Transitions below |
| `processed` | `int` | Traces processed so far; starts at 0 |
| `total` | `int \| None` | `None` (indeterminate) until extraction completes, then fixed |
| `start_timestamp` | `datetime` | Set at creation, UTC |
| `end_timestamp` | `datetime \| None` | Set once, the first time the run reaches *any* terminal `RunStatus` (including `DELIVERY_FAILED`); a later successful retry does not move it — retry is delivery-only, not trace processing, and FR-009 ties the end timestamp to reaching "a final status," which the run already did |
| `errors` | `list[PerTraceError]` | Appended to as per-trace failures occur; empty ⇒ clean run |
| `_results` | `dict[str, EvaluationResult]` | Private; trace_id → per-trace `EvaluationResult` (M3.1 type), retained for handoff/retry as long as this object is reachable (research.md R6) |
| `_retry_lock` | `threading.Lock` | Private; excluded from `repr`/equality; serializes `retry_delivery` (FR-007 last clause) |

`progress` is a derived read (not a stored field, so it can never drift from `processed`/`total`):
`None` while `total is None`; otherwise `1.0` for a zero-trace run (`total == 0`, per FR-008's
explicit "treated as complete rather than requiring division by zero"), else
`processed / total`.

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
         │ (all traces processed)
         ▼
   handoff.deliver(run, results)
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
             handoff.deliver(run, run._results) again
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

## `ResultHandoff` (`evaluation/result_handoff.py`)

Abstract collaborator, one method:

```python
class ResultHandoff(ABC):
    @abstractmethod
    def deliver(self, run: EvaluationRun, results: dict[str, EvaluationResult]) -> None:
        """Hand off completed results. Raise on failure — Evaluator maps that to DELIVERY_FAILED."""
```

No concrete production implementation ships in this milestone (research.md R6) — durable
persistence (`EvaluationRepository`) and downstream notification (`ResultPublisher`) are
separately-specified, future capabilities per the spec's Assumptions.

## `Evaluator` (`evaluation/evaluator.py`)

The orchestrator (spec's Key Entity). Composes, does not reimplement:

| Collaborator | Role | Reused from |
|---|---|---|
| `ConfigManager` | bot-existence check (R4) | M1 |
| `TraceCollector` | extraction (bulk, per bot/period) | M2.1 |
| `TraceNormalizer` | per-trace normalization | M2.2 |
| `EvaluationOrchestrator` | per-trace metric evaluation, given override thresholds (R3) | M3.1 |
| `ResultHandoff` | delivery of completed results | this milestone (interface only) |

Public surface — see `contracts/evaluator-api.md`.

## Key entity cross-reference (spec → implementation)

| Spec Key Entity | Type | File |
|---|---|---|
| `EvaluationConfig` | `EvaluationConfig` (dataclass) | `evaluation/evaluation_config.py` |
| `EvaluationRun` | `EvaluationRun` (dataclass) + `RunStatus` (enum) | `evaluation/evaluation_run.py` |
| `PerTraceError` | `PerTraceError` (dataclass) | `evaluation/evaluation_run.py` |
| `Evaluator` | `Evaluator` (class) | `evaluation/evaluator.py` |

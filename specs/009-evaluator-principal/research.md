# Phase 0 Research: Evaluator Principal (M4.2)

Every "unknown" below is resolved against the existing codebase (M2.1 collection, M2.2
normalization, M3.1 metric evaluation, M4.1 synthetic/persistence conventions) rather than
external libraries — this milestone composes already-specified capabilities per the spec's
Assumptions section. No DeepEval/LangChain native class is a candidate for the orchestration
logic itself (Principle II/III scope boundary: `Evaluator` is a project-local orchestration
abstraction, like `TraceExtractor`/`EvaluationStrategy`, not a DeepEval metric/dataset/model).

## R1: How does `EvaluationConfig` satisfy FR-013/FR-014/FR-015 with minimal validation code?

**Decision**: Model metrics and thresholds as a single field, `metric_thresholds: dict[str,
float]` (metric name → threshold), instead of a `list[str]` of metric names plus a parallel
`dict[str, float]` of thresholds.

**Rationale**: FR-015 requires "metric names ... unique and ... one-to-one correspondence with
thresholds; a duplicate metric name, missing threshold, or threshold without a corresponding
metric MUST cause rejection." A Python `dict` cannot hold a duplicate key and cannot have a
metric without a threshold or a threshold without a metric — the one-to-one, no-duplicates
invariant is structurally guaranteed by the chosen type, so FR-015 needs zero runtime
cross-validation code. This mirrors the project's existing preference for structural guarantees
over runtime checks (e.g., `TraceFilter.__post_init__` for `start_date < end_date`,
`BotType(str, Enum)` for closed vocab).

**Alternatives considered**:
- Two parallel structures (`metrics: list[str]`, `thresholds: dict[str, float]`) — rejected:
  requires explicit duplicate/missing/extra cross-validation that a dict eliminates for free.
- `list[tuple[str, float]]` — rejected: still allows duplicate metric names; no advantage over a
  dict and loses O(1) lookup used by validation/threshold-override plumbing.

**Remaining validation** (still required, not eliminated by the type choice): every key must be a
metric `MetricFactory._registry` knows (FR-014, reuses `UnknownMetricError` — same class the
existing `EvaluationOrchestrator` raises for the identical condition, see R3) and every value must
be within `[0.0, 1.0]` (FR-002, reuses `InvalidThresholdError` — same shape/message as the
orchestrator's own threshold-range check).

## R2: How does `Evaluator` return an `EvaluationRun` immediately while processing continues?

**Decision**: `Evaluator.start()` validates synchronously, constructs the `EvaluationRun`, starts
a daemon `threading.Thread` running the pipeline against that same object, and returns the object
immediately. The background thread mutates the run's attributes in place (`status`, `processed`,
`total`, `errors`, `end_timestamp`); callers holding the returned reference observe those
mutations directly — there is no separate "refresh" or "poll" call.

**Rationale**: Every step already wired for this milestone is synchronous/blocking Python:
`TraceCollector.collect()` makes one blocking HTTP call via `TraceRepository`, and
`TraceNormalizer.normalize()` is pure CPU-bound synchronous code. Only
`EvaluationOrchestrator.evaluate()` (M3.1) is a coroutine. There is no FastAPI/ASGI event loop
guaranteed to be running when `start()` is called — Assumptions explicitly leave the trigger
(manual call, `APScheduler` cron job, or a future API endpoint) out of scope, and `APScheduler`
itself runs jobs in worker threads by default. A plain background thread is therefore the only
option that behaves identically regardless of caller context, needs no new dependency, and keeps
`Evaluator` usable from a synchronous script exactly as `SyntheticDatasetGenerator.generate()` is
today. Each per-trace call to `EvaluationOrchestrator.evaluate()` is driven with `asyncio.run(...)`
inside the background thread — a fresh event loop per trace, mirroring how
`contracts/evaluation-api.md` already tells synchronous callers to invoke `metric.measure()`.

CPython's GIL makes single-writer/multi-reader attribute mutation on the shared `EvaluationRun`
instance safe without extra locking; the one place true mutual exclusion is required — serializing
concurrent retry attempts — uses a `threading.Lock` (R5).

**Alternatives considered**:
- `asyncio.create_task()` — rejected: requires a running event loop at call time, which callers
  triggering a run from a synchronous context (script, cron) do not have.
- A process/thread pool with a job-id registry (Celery-like) — rejected: no such infrastructure
  exists in this project (Technology Stack has no task queue), and Assumptions defer the trigger
  mechanism to a separate milestone; adding one here is scope creep the constitution's
  extensibility principle does not require.
- Fully synchronous `start()` (block until the run finishes, like `SyntheticDatasetGenerator.
  generate()`) — rejected: directly contradicts FR-003 and US2 Scenario 4, which require the
  handle to return before processing completes.

## R3: How are per-run threshold overrides applied without mutating `bots.yaml` (FR-013)?

**Decision**: Extend `EvaluationOrchestrator.evaluate()` with an optional keyword-only
`thresholds: dict[str, float] | None = None` parameter. When provided, `_resolve_thresholds` uses
that mapping directly instead of reading `bots.{bot_id}.metrics.{name}.threshold` from
`ConfigManager`. `Evaluator` always passes the run's already-validated `metric_thresholds`
explicitly; existing M3.1 callers that omit the argument keep today's config-lookup behavior
unchanged (backward compatible, additive change only).

**Rationale**: `EvaluationOrchestrator` (M3.1) is the single place that turns a `(bot_id,
metric_name)` pair into an instantiated, thresholded `MetricBase` via `MetricFactory` — that
responsibility must not be duplicated in `Evaluator` (Principle I: single, well-defined
responsibility per class; duplicating threshold/timeout/judge resolution here would be exactly the
kind of reimplementation the constitution's DRY intent forbids). `ConfigManager` remains the sole
config reader (Principle V) — `Evaluator` never reads `bots.yaml` for thresholds itself, it only
reads it once via `BotMetricConfigResolver`-adjacent lookups for bot-existence validation (R4) and
supplies already-resolved values to the orchestrator. `bots.yaml`/the bot's stored defaults are
never written to, satisfying "the bot's stored defaults MUST remain unchanged after the run."

**Alternatives considered**:
- `Evaluator` constructing `MetricBase` instances itself via `MetricFactory.create()` directly —
  rejected: duplicates timeout/judge resolution and per-metric options
  (`BotMetricConfigResolver.resolve_options`) already implemented in `EvaluationOrchestrator`.
- A second `ConfigManager` entry namespace (e.g. writing overrides into a scoped in-memory copy of
  config) — rejected: `ConfigManager` is an explicit process-wide Singleton (Principle VI); giving
  it call-scoped mutable state contradicts "one instance per process, no re-reads" and would leak
  across concurrent runs (FR-012).

## R4: How is an unknown `bot_id` rejected before run state is created (FR-002)?

**Decision**: Reuse the exact check `TraceNormalizer` and `TraceCollector` already depend on
transitively — `ConfigManager.instance().get(f"bots.{bot_id}.bot_type")` — catching `ConfigError`
and re-raising a new `UnknownBotError(bot_id)` from `deepeval_platform/evaluation/errors.py`,
following the file's stated convention ("each message carries every diagnostic field a caller
would need without reformatting", same shape as `UnmappedBotError` in the normalization domain).

**Rationale**: `bot_type` is the one key every configured bot in `bots.yaml` unconditionally
declares (`StrategyFactory`, `TraceNormalizer` both depend on it); checking it is the same
"is this bot configured at all" test the rest of the codebase already uses, so this needs no new
`bots.yaml` schema and no new config key.

**Alternatives considered**:
- `StrategyFactory.create(bot_type)` as the validation call — rejected: conflates "is `bot_id`
  configured" with "is the *configured* `bot_type` value one `StrategyFactory` recognizes"; the
  spec's unknown-bot case is about `bot_id`, not about a malformed `bot_type` value, which is an
  existing, separately-handled `InvalidBotTypeError` case one layer down.

## R5: How is `PerTraceError` populated per pipeline stage, and is "extraction" reachable?

**Decision**: `PerTraceError.stage` is `Literal["extraction", "normalization", "evaluation"]`
(same modeling convention as `DocumentFailure.stage: Literal["readability", "parsing"]` in M4.1).
In this milestone's implementation, only `"normalization"` (a `TraceNormalizer.normalize()`
exception, e.g. `UnmappedBotError`/`FieldMappingTypeError`) and `"evaluation"` (any exception
`EvaluationOrchestrator.evaluate()` raises for one trace) are ever produced. `"extraction"` is
defined for parity with FR-010/the data model's stated vocabulary and for future extractors that
fetch traces one-at-a-time, but `TraceCollector.collect()` (M2.1) is one bulk call — if it raises,
every trace in the period is equally affected, which is exactly the edge case the spec calls
"trace source is entirely unreachable" and routes to `UNABLE_TO_RUN`, not to a per-trace error.

**Rationale**: This is the literal edge-case distinction the spec draws: "a single trace being
malformed" (per-trace, isolated) vs. "the trace source is entirely unreachable" (whole-run,
`UNABLE_TO_RUN`). Given the current `TraceCollector`/`TraceRepository` contract, there is no
partial-extraction outcome — extraction for a run either produces the full candidate list or
raises once for the whole call. Recording this now avoids a future reader assuming dead code when
no test exercises `PerTraceError(stage="extraction", ...)`.

Each `PerTraceError` reuses the existing `sanitize_error()` helper from `evaluation/errors.py` for
its message (same redaction of bearer tokens/opaque credentials already applied to
`MetricResult.error`), plus `type(exc).__name__` as the stable `error_code`.

## R6: How does result handoff/delivery-retry work without building persistence (FR-007)?

**Decision**: A small `ResultHandoff` ABC (`deepeval_platform/evaluation/result_handoff.py`) with
one method, `deliver(run: EvaluationRun, results: dict[str, EvaluationResult]) -> None`, that may
raise on failure. `Evaluator` takes an injected `ResultHandoff` implementation (constructor
parameter, like every other collaborator in this codebase); this milestone ships no concrete
non-trivial implementation — durable persistence (`EvaluationRepository`) and downstream
notification (`ResultPublisher`, Observer pattern) are explicitly separate, future milestones per
the spec's Clarifications and the constitution's own pattern table. Tests and any interim caller
supply their own `ResultHandoff` (e.g. an in-memory collecting stub); production wiring of a real
handoff is out of scope here, exactly as `EvaluationRepository`/`ResultPublisher` wiring was left
out of M4.1 for the same reason.

`EvaluationRun` retains its completed per-trace results as a private instance attribute
(`_results: dict[str, EvaluationResult]`). `Evaluator.retry_delivery(run: EvaluationRun)` takes the
run object itself — not a `run_id` looked up from some server-side registry — validates
`run.status is RunStatus.DELIVERY_FAILED` (else `InvalidRetryStateError`, no state change),
acquires a non-blocking `threading.Lock` stored on the run (`run._retry_lock`) to serialize
concurrent attempts (else `RetryInProgressError`, no state change), and calls
`self._handoff.deliver(run, run._results)` again — no re-extraction, re-normalization, or
re-evaluation.

**Rationale**: The clarification "retain ... results for as long as its `EvaluationRun` handle
remains reachable" is a direct pointer to normal Python reference-counting/GC semantics, not to a
server-side cache with its own eviction policy. Storing results as an attribute *on the run object
itself* makes "reachable" literally mean "not yet garbage collected" — no `Evaluator`-side
`dict[UUID, EvaluationRun]` registry is needed at all, which also means `Evaluator` carries no
run-lifecycle state of its own and trivially satisfies FR-012 (independent runs cannot interfere —
there is no shared collection they contend over). This also answers "how does a caller check
status" (US2): the caller already holds the mutated handle from `start()`; there is no separate
`get_run(id)` lookup API to design or keep consistent.

**Alternatives considered**:
- `Evaluator`-side `dict[UUID, EvaluationRun]` run registry with `get_run`/`retry_delivery` taking
  a `run_id` — rejected: keeps every run alive for the process's lifetime (unbounded memory growth
  across many runs), contradicts the "while ... reachable" wording, and adds an API surface
  (`get_run`) the spec never asks for — US2's "checking its state" is fully satisfied by reading
  the handle already returned by `start()`.
- Making `retry_delivery` itself asynchronous/backgrounded like `start()` — rejected: nothing in
  FR-007/the clarifications requires retry to return before the (single) delivery attempt
  completes; keeping it a blocking call is simpler and still satisfies "exactly one new delivery
  attempt" (SC-007) without adding thread-management code for a second async path.

## R7: UTC normalization and half-open period semantics

**Decision**: `EvaluationConfig.__post_init__` normalizes `period_start`/`period_end` to UTC —
naive `datetime` values are treated as already UTC (`.replace(tzinfo=timezone.utc)`), aware values
are converted (`.astimezone(timezone.utc)`) — then validates `period_start < period_end` (strict,
per clarification: equal boundaries are invalid). `TraceCollector.collect()` is called with a
`TraceFilter(bot_id, start_date=period_start, end_date=period_end)`; `TraceFilter.__post_init__`
already enforces `start_date < end_date`, so the half-open `[start, end)` contract is carried
through unchanged into the existing M2.1 collection layer without modification there.

**Rationale**: This matches the existing convention in `EvaluationRepository.get_by_bot`, which
already treats naive `datetime` as UTC and only rejects non-UTC *aware* offsets. `TraceFilter`
already models exactly the half-open, `start < end` contract this feature needs — no change to
`collection/trace_filter.py` or `TraceRepository` is required; `Evaluator` only needs to normalize
before constructing the filter.

## Post-implementation gate status

Not yet started — implementation begins with `/speckit-tasks`. This section will be completed at
the end of the implementation phase, following the M4.1 precedent.

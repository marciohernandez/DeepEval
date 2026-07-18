# Phase 0 Research: Evaluator Principal (M4.2)

Every "unknown" below is resolved against the existing codebase (M2.1 collection, M2.2
normalization, M3.1 metric evaluation, M4.1 synthetic/persistence conventions) and the current
DeepEval API review recorded below. This milestone composes already-specified capabilities per the
spec's Assumptions section; it does not reimplement DeepEval metric scoring.

## DeepEval-first native capability review

**Reviewed**: 2026-07-17 against the official DeepEval documentation and the repository's installed
DeepEval 4.0.7 API (`pyproject.toml` requires `deepeval>=4.0.6`). Sources consulted:

- [DeepEval evaluation introduction](https://github.com/confident-ai/deepeval/blob/main/docs/content/docs/evaluation-introduction.mdx):
  `evaluate(test_cases, metrics, ...)` as the programmatic batch evaluation entry point, returning
  `deepeval.evaluate.types.EvaluationResult`.
- [DeepEval API reference](https://github.com/confident-ai/deepeval/blob/main/docs/public/llms-full.txt):
  `AsyncConfig(run_async, throttle_value, max_concurrent)`,
  `ErrorConfig(ignore_errors, skip_on_missing_params)`, and `DisplayConfig`.
- [DeepEval manual agent instrumentation](https://github.com/confident-ai/deepeval/blob/main/docs/snippets/evaluation/cicd-agent-framework-tabs.mdx):
  `@observe`, `EvaluationDataset.evals_iterator`, and `assert_test` for traced application or CI
  evaluation flows.

**Native capabilities that MUST continue to be reused**:

- DeepEval metric implementations and their native `a_measure()` methods remain the scoring engine
  behind the existing M3.1 `MetricBase` adapters and `EvaluationOrchestrator`.
- Native metric thresholds remain constructor-level metric configuration; the project's per-run
  threshold override is supplied when `MetricFactory` constructs those native metrics.
- `evaluate()` can evaluate a completed collection of `LLMTestCase` or
  `ConversationalTestCase` values concurrently. `AsyncConfig` controls test-case/metric
  concurrency, `ErrorConfig` controls metric/test error handling, and the call returns a native
  result aggregate after evaluation finishes.

**Why the native batch API does not satisfy the M4.2 Evaluator contract as-is**:

- It does not extract project `TraceRecord` values from Langfuse or normalize them through the
  existing `TraceNormalizer`; it starts from already-built DeepEval test cases.
- `evaluate()` is a completing call that returns its result aggregate after evaluation; it does
  not return this feature's immediately-queryable `EvaluationRun` handle and does not expose this
  feature's processed/total counts or first-terminal `wait(timeout)` contract.
- `AsyncConfig` configures internal concurrency but does not provide the required run lifecycle or
  stage-level progress API. `DisplayConfig` provides presentation, not queryable domain state.
- `ErrorConfig(ignore_errors=True)` can isolate evaluation errors, but it does not model this
  feature's extraction-, normalization-, and evaluation-stage `PerTraceError` contract or its
  distinction between `UNABLE_TO_RUN`, `COMPLETED_WITH_FAILURES`, and `DELIVERY_FAILED`.
- The native result aggregate does not publish to a requester-supplied `ResultObserver`, retain the
  project's per-trace result mapping for inspection, or retry only a failed delivery without
  reevaluating test cases.

**Decision**: Keep `Evaluator` as a project-local integration/orchestration abstraction over the
already-DeepEval-backed M3.1 `EvaluationOrchestrator`. Its custom responsibility is limited to the
M4.2 lifecycle missing from DeepEval's batch API: extraction, normalization sequencing, live run
state, stage-aware failure routing, and observer delivery/retry. `Evaluator` MUST delegate scoring
to `EvaluationOrchestrator` and MUST NOT reproduce native metric measurement logic. Direct use of
DeepEval `evaluate()` was considered and rejected for this layer because adapting its completing
batch result back into the required live lifecycle would still require the custom orchestration and
would discard the existing M3.1 timeout/result/error contract.

## R1: How does `EvaluationConfig` satisfy FR-013/FR-014/FR-015 with minimal validation code?

**Decision**: Model submitted metrics and thresholds as `list[MetricThreshold]`, where each entry
contains a metric name and threshold. Validate the preserved entries, then construct an internal
`dict[str, float]` for threshold lookup.

**Rationale**: FR-015 requires duplicate submissions to be rejected. A Python `dict` loses that
information before validation, so it cannot satisfy the rejection contract. A value object entry
always couples one metric with one threshold, preventing missing or extra thresholds, while the
list preserves duplicate metric names until `Evaluator.start()` rejects them. The validated
internal mapping retains O(1) lookup for threshold-override plumbing.

**Alternatives considered**:
- Two parallel structures (`metrics: list[str]`, `thresholds: dict[str, float]`) — rejected:
  they require cross-validation and can represent missing or extra thresholds.
- A caller-supplied `dict[str, float]` — rejected: duplicate metric submissions are lost before
  FR-015 validation can reject them.

**Validation**: the list must be non-empty; names must be unique (`DuplicateMetricError`); every
name must contain a non-whitespace character and satisfy `MetricFactory.is_registered(name)`
(FR-014, reuses `UnknownMetricError`); and
every threshold must be a non-boolean `int`/`float` satisfying
`math.isfinite(float(value)) and 0.0 <= float(value) <= 1.0` (FR-002, reuses
`InvalidThresholdError`). Strings are rejected rather than coerced. Only after every entry passes
does `Evaluator` convert valid values to float in its internal mapping. This explicit finite check
prevents comparison formulations such as `value < 0 or value > 1` from accidentally accepting
`NaN`.

## R2: How does `Evaluator` return an `EvaluationRun` immediately while processing continues?

**Decision**: `Evaluator.start()` validates synchronously, constructs the `EvaluationRun`, starts
a daemon `threading.Thread` running the pipeline against that same object, and returns the object
immediately. The background thread updates private run state only through public methods guarded
by a per-run `threading.RLock`; synchronized properties expose individual values.
`EvaluationRun.snapshot()` captures an immutable point-in-time `EvaluationRunSnapshot` containing
status, counts, derived progress, timestamps, detached errors/results, and failure information in
one critical section. `EvaluationRun.wait(timeout)` uses a private `threading.Event` set on the
first terminal transition, so callers and tests can deterministically wait for completion without
a refresh API or arbitrary polling delay.

The worker entrypoint wraps its planned pipeline handling in an outer `except Exception` guard.
If an unexpected error escapes without identifying a trace, it stores `sanitize_error(exc)` in
`run.failure_message` and transitions the run to `UNABLE_TO_RUN`. This guard does not replace
per-trace handling: identified extraction, normalization, and evaluation failures continue to be
recorded as `PerTraceError` and allow the run to complete with failures.

**Rationale**: Every step already wired for this milestone is synchronous/blocking Python:
`TraceCollector.collect_all()` makes blocking paginated HTTP calls via `TraceRepository`, and
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

The GIL is not treated as a synchronization contract: multi-field transitions, list updates, and
derived progress reads must remain coherent independently of interpreter implementation details.
The state `RLock` is held only while reading/updating in-memory state and is released before calling
the collector, normalizer, orchestrator, or observer. A separate non-blocking retry lock serializes
delivery attempts. Retry status validation and retry-lock acquisition happen while holding the
state lock; on successful retry, the final status is recorded before releasing the retry lock, so
no second retry can enter between publication success and the status transition.

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
`ConfigManager`. `Evaluator` validates the submitted `list[MetricThreshold]`, then passes its
internal `dict[str, float]` mapping explicitly; existing M3.1 callers that omit the argument keep today's config-lookup behavior
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
transitively — `ConfigManager.instance().get(f"bots.{bot_id}.bot_type")`. Translate only the
manager's explicit missing-key outcome for that exact path, or an empty returned value, to the new
`UnknownBotError(bot_id)` from `deepeval_platform/evaluation/errors.py`. Parsing/loading and other
`ConfigError` failures propagate unchanged, following the file's stated convention that each
domain exception carries every diagnostic field a caller needs without reformatting.

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
This milestone adds `TraceCollector.collect_all()` returning `TraceCollectionResult`, containing
successfully extracted traces plus identified `TraceCollectionError` values. `Evaluator` converts
the latter to extraction-stage `PerTraceError` entries. A setup/connectivity failure before any
affected trace can be identified remains a whole-run `UNABLE_TO_RUN` outcome.

**Rationale**: This implements the specification's required distinction between an identified
single-trace extraction failure (per-trace, isolated) and an entirely unreachable trace source
(whole-run, `UNABLE_TO_RUN`). The collection result makes this distinction explicit instead of
leaving `PerTraceError(stage="extraction")` unreachable.

Each `PerTraceError` reuses the existing `sanitize_error()` helper from `evaluation/errors.py` for
its message (same redaction of bearer tokens/opaque credentials already applied to
`MetricResult.error`). Its `PerTraceErrorCode` is selected only from the failed stage:
`EXTRACTION_FAILED`, `NORMALIZATION_FAILED`, or `EVALUATION_FAILED`; it MUST NOT expose
`type(exc).__name__`, which is an implementation detail and can change across dependencies.

## R6: How does result publication/delivery-retry work without building persistence (FR-007)?

**Decision**: `Evaluator.start(config, observer)` receives exactly one requester-supplied
`ResultObserver`. It stores that observer privately on the resulting `EvaluationRun` and invokes
the injected `ResultPublisher` through `publish(run, results, observer)`. This applies the
constitution's mandatory Observer pattern without treating every observer as a global subscriber.
Tests use separate in-memory observers; durable persistence (`EvaluationRepository`) and
downstream destination observers remain separate future capabilities.

After all traces are processed and results are retained, the initial delivery transitions the run
from `IN_PROGRESS` to non-final `DELIVERING` before invoking the observer. Consequently, observer
code cannot see a run that still claims to be evaluating traces, while `wait()` remains unsignaled
until publication succeeds (`COMPLETED`/`COMPLETED_WITH_FAILURES`) or raises (`DELIVERY_FAILED`).
The first `end_timestamp` is set only at that final transition.

`EvaluationRun` retains its completed per-trace results as a private instance attribute
(`_results: dict[str, EvaluationResult]`). `retain_results()` stores `deepcopy(results)` so the
caller's working dictionary and nested result objects cannot remain aliases of canonical run
state. The public `results` property and each `delivery_payload()` call return a fresh
`MappingProxyType(deepcopy(_results))`. `delivery_payload()` returns exactly
`(results_snapshot, observer)`, consumed as `ResultPublisher.publish(run, results_snapshot,
observer)`. The proxy rejects key replacement/removal, while the deep
copy ensures mutation of a nested `EvaluationResult`, `MetricResult`, or `ErrorDetail` affects only
that one snapshot. `Evaluator.retry_delivery(run: EvaluationRun)` takes the run object itself — not
a `run_id` looked up from some server-side registry — and calls `run.begin_retry()`. That method
atomically validates `DELIVERY_FAILED` and acquires the non-blocking retry guard under the state
lock, raising `InvalidRetryStateError` or `RetryInProgressError` without changing state. The
Evaluator unpacks `results_snapshot, observer = run.delivery_payload()`, publishes with
`ResultPublisher.publish(run, results_snapshot, observer)`, and, on success, calls a run-owned
`complete_delivery(status)` operation that records the restored completion status and clears the
observer atomically before releasing the retry guard in `finally` — no
  re-extraction, re-normalization, or re-evaluation. Successful initial publication or retry
  releases the run's private observer reference in the same synchronized action as completion;
  failed publication retains it because retry remains valid. A zero-trace run follows the same
  path and publishes exactly one empty detached mapping.

A retry leaves `run.status == DELIVERY_FAILED` while the observer call is in flight. It does not
reuse `DELIVERING`: the existing delivery-failed outcome and the acquired retry guard together let
a concurrent request receive the required `RetryInProgressError` rather than being misclassified
as an invalid-state request. Success restores the original completion outcome; failure leaves the
status unchanged.

Each retry creates a new detached snapshot from the canonical retained copy. Therefore an observer
that mutates its first delivery payload before raising cannot influence requester inspection or the
payload supplied to a later retry.

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
per clarification: equal boundaries are invalid). A
`TraceFilter(bot_id, start_date=period_start, end_date=period_end)` is passed to
`TraceCollector.collect_all()`; `TraceFilter.__post_init__` already enforces
`start_date < end_date`, and `collect_all()` applies the half-open boundary locally after paginated
retrieval (R8).

**Rationale**: This matches the existing convention in `EvaluationRepository.get_by_bot`, which
already treats naive `datetime` as UTC and only rejects non-UTC *aware* offsets. `TraceFilter`
already models exactly the half-open, `start < end` contract this feature needs — no change to
`collection/trace_filter.py` or `TraceRepository` is required; `Evaluator` only needs to normalize
before constructing the filter. Non-`datetime` boundaries are rejected with `TypeError` before
timezone operations. Empty or whitespace-only `bot_id` and metric names are invalid before run
creation.

## R8: Exhaustive collection without breaking M2.1's 500-trace contract

**Decision**: Preserve `TraceCollector.collect()` exactly as specified by M2.1 (most recent 500,
with a truncation warning) and add `TraceCollector.collect_all()` for evaluation runs.
`collect_all()` delegates to a new `TraceRepository.get_all_by_date_range()` operation, which calls
Langfuse `GET /api/public/traces` with `page`, one fixed `limit`, and stable `order_by`, appends each response's `data`, and
continues through `meta.totalPages`. The repository converts all rows to `TraceRecord`; the
collector then applies the platform extractor, deterministic timestamp ordering, and an explicit
local `start <= start_time < end` check without slicing the result.

Before constructing `TraceCollectionResult`, `collect_all()` rejects every successful/error outcome
whose `trace_id` is empty or whitespace-only; collection fails as a whole because inventing an ID
would break requester correlation. It then groups every remaining outcome by `trace_id`. A group
with exactly one outcome is retained. Any ID with multiple
outcomes is represented by one sanitized `TraceCollectionError` and no successful record,
regardless of whether the repeated records have equal payloads. This avoids silently selecting a
canonical payload from inconsistent pages and establishes the invariant required by the evaluator's
`dict[trace_id, EvaluationResult]`: one logical ID produces at most one result.

**Documentation/API validation**: The official Langfuse public API documentation defines list
responses as `{data, meta}` and the installed Langfuse 4.13.0 API exposes trace-list `page`, `limit`,
`from_timestamp`, `to_timestamp`, and `order_by` parameters. Its `MetaResponse` contains `page`,
`limit`, `total_items`, and `total_pages`. The direct HTTP repository uses the corresponding REST
fields and treats missing/malformed pagination metadata as a retrieval failure rather than silently
claiming exhaustive coverage. Repeated pages or rows, changing totals, and premature empty pages
also fail rather than loop or return partial data.

**Rationale**: Changing `collect()` to return more than 500 would violate M2.1 FR-001 and break a
shipped public behavior. Reusing it unchanged would violate M4.2 FR-004 for large periods. The
additive method gives each use case an explicit contract and keeps pagination in the repository,
the constitution-mandated owner of storage queries. Local boundary filtering makes M4.2's
half-open interval independent of endpoint boundary inclusivity and prevents an end-boundary trace
from entering the run.

**Alternatives considered**:
- Remove or raise `MAX_INTERACTIONS` in `collect()` — rejected because it breaks M2.1's mandatory
  capped contract and existing tests/callers.
- Call the repository once and bypass only the collector slice — rejected because Langfuse's list
  endpoint is paginated and a single response cannot establish exhaustive coverage.
- Put the page loop in `Evaluator` — rejected because raw retrieval belongs exclusively to
  `TraceRepository` under Constitution Principle VI and M2.1 FR-002.
- Keep the first or last duplicate record — rejected because page ordering must not silently decide
  which conflicting payload is evaluated.
- Preserve duplicate records in a list and let the result dictionary overwrite — rejected because
  it violates FR-006's one-result-per-trace guarantee and hides data loss.

## Post-implementation gate status (Phase 8, 2026-07-17)

T038-T041/T048/T056/T057 executed exactly as specified in tasks.md/quickstart.md. Results:

- **T038 (focused feature suite)**: `uv run pytest tests/unit/evaluation/test_evaluation_config.py
  tests/unit/evaluation/test_evaluation_run.py tests/unit/evaluation/test_evaluator.py
  tests/unit/evaluation/test_evaluation_orchestrator.py
  tests/unit/evaluation/metrics/test_metric_factory.py
  tests/unit/evaluation/test_result_publisher.py tests/unit/collection/test_trace_collector.py
  tests/unit/repositories/test_trace_repository.py -v` — 206 passed, 0 failed.
- **T039 (integration verification)**: `uv run pytest tests/integration/test_evaluator_flow_integration.py
  -v -rs -m integration` — 1 passed, 0 skipped. No `.env` read, no external network access, no
  credential dependency (in-process HTTP stub server serving the Langfuse `{data, meta}` pagination
  contract, plus a deterministic `DeepEvalBaseLLM` fake for the judge boundary).
- **T040 (coverage)**: `uv run pytest --cov=deepeval_platform --cov-report=term-missing
  --cov-report=json --cov-fail-under=80` — total project coverage 98.22% (gate: >=80%). Every
  new/changed M4.2 module: `evaluation_config.py` 100%, `evaluation_run.py` 99% (one uncovered
  line — `__repr__`), `result_publisher.py` 100%, `evaluator.py` 99% (one uncovered line — the
  defensive "empty-but-not-raised `bot_type`" branch), `evaluation_orchestrator.py` 87%
  (pre-existing M3.1 branches; the additive `thresholds` parameter itself is fully covered),
  `metric_factory.py` 100%, `errors.py` 100%, `trace_collector.py` 99%, `trace_repository.py` 100%.
  A full unsandboxed `uv run pytest` (all tests, no `-m` filter) was also run: 849 passed, 8
  skipped, 7 failed — the 7 failures (`test_evaluation_repository_integration.py::
  TestSchemaValidationIntegration`, `test_llm_factory_integration.py`'s real Anthropic/OpenRouter
  calls, `test_qdrant_provider_integration.py` x4) are pre-existing and unrelated to M4.2: this
  sandbox has no live Supabase/Anthropic/OpenRouter/Qdrant credentials, matching the exact M4.1
  precedent's finding. Zero regressions attributable to M4.2.
- **T048 (zero-hardcode scan)**: `detect-secrets` is not installed in this environment; ran the
  documented fallback (`git diff --check` — clean; a credential/token/non-local-host regex across
  `deepeval_platform/evaluation`, `deepeval_platform/collection`, `deepeval_platform/repositories`,
  and the corresponding unit/integration test directories). 4 matches, all reviewed and cleared: two
  are pre-existing test fixtures with obviously-fake values (`api_key="test-openai-key"`,
  `access_token="tok"`) unrelated to M4.2; one is an XML namespace URI inside an unrelated
  pre-existing DOCX fixture; one is this feature's own integration test constructing a URL from its
  in-process stub server's `(host, port)` — always `127.0.0.1` at runtime, flagged only because the
  regex cannot see through the f-string. No real credential, API key, token, password, or
  non-local environment-specific host is present. All new configuration access (`LANGFUSE_HOST`,
  `bots.{bot_id}.bot_type`, etc.) continues to go exclusively through `ConfigManager`.
- **T056 (Python 3.11 compatibility) — blocked by a pre-existing, unrelated repo inconsistency, not
  a code defect**: `pyproject.toml` declares `requires-python = ">=3.13"` (set 2026-06-22, commit
  `e8deaa6`, long before this feature), which contradicts the constitution's stated "Core runtime:
  Python `^3.11`". `uv python install 3.11` succeeded; `uv sync --python 3.11` against an isolated
  venv was then refused by `uv` itself: `error: The requested interpreter resolved to Python
  3.11.15, which is incompatible with the project's Python requirement: >=3.13`. This is a
  project-wide configuration inconsistency predating and unrelated to M4.2; reconciling the
  constitution's `^3.11` against `pyproject.toml`'s `>=3.13` is outside this feature's scope, and
  was not silently patched. The full feature suite (811 unit tests + 1 integration test) was
  verified GREEN under this repository's actual development interpreter, Python 3.13.13.
- **T057 (TDD RED-before-GREEN git-history audit) — practice confirmed in-session; git history only
  partially auditable at the chosen commit granularity**: `git log --reverse --name-status` from
  the task-generation commit (`d270041`) forward shows commits bundling every test file and every
  production file for a phase together (e.g. `0a091fe` for Phase 2, `27d303e` for all of Phase 3);
  Phase 4-6 changes to `evaluator.py`/`test_evaluator.py` remained uncommitted in the working tree
  at audit time. Work proceeded phase-by-phase per explicit instruction: for every task, the
  corresponding test was written, run, and observed to fail (RED — `ImportError`/`AttributeError`/
  `AssertionError` against not-yet-existing or not-yet-updated production code) before the matching
  production code was written and re-run to GREEN; this was verified live via `uv run pytest`
  after each test-writing step throughout the session. Because commits land at phase granularity
  rather than per task, `git log` alone cannot reconstruct that ordering after the fact — a commit's
  diff shows a test and its implementation together, not as two ordered commits. This satisfies the
  TDD *practice* (verified in-session, described above) but not the *letter* of a pure git-log audit.
  Recorded as an honest limitation of the chosen commit workflow, not an implementation defect;
  finer-grained commits would be required to make this gate fully self-evident from git history
  alone, and that choice is left to the project owner.

**DeepEval-first boundary reconfirmed**: no part of this implementation touches native metric
scoring. `Evaluator` composes `TraceCollector`/`TraceNormalizer`/`EvaluationOrchestrator`/
`ResultPublisher` and delegates every per-trace measurement to the already-DeepEval-backed M3.1
`EvaluationOrchestrator.evaluate()` (extended only with the additive `thresholds` override
parameter specified in R3 above); no native `Metric`/`a_measure()` logic was reimplemented. The
lifecycle capabilities `Evaluator` adds — extraction/normalization sequencing, live run state,
stage-aware failure routing, and observer delivery/retry — remain exactly the set identified in the
DeepEval-first native capability review above as absent from DeepEval 4.0.7's own batch `evaluate()`
API.

# Quickstart: Validating the Evaluator Principal (M4.2)

## Prerequisites

- M2.1 (`TraceCollector`/`TraceRepository`), M2.2 (`TraceNormalizer`), and M3.1
  (`EvaluationOrchestrator`, `MetricFactory`) are already implemented and green — this milestone
  composes them, it does not reimplement any of their behavior.
- `config/bots.yaml` has at least one bot with `bot_type`, `platform`, and `field_mapping`
  declared (e.g. `test_rag_bot`).
- `config/settings.yaml` has `evaluation.llm_judge.provider`/`model` and
  `evaluation.metric_timeout_seconds` set, as required by `EvaluationOrchestrator` already.
- No new environment variables or `bots.yaml`/`settings.yaml` keys are introduced by this
  milestone (`Evaluator` only reads `bots.{bot_id}.bot_type` for existence checks and delegates
  everything else to already-wired collaborators) — `.env.example` needs no changes.

## Strict TDD workflow

For each behavior below, add its test and run it to observe RED before writing the corresponding
production code; implement the minimum to reach GREEN; refactor while green. Merely creating test
files does not satisfy this gate.

```bash
uv run pytest tests/unit/evaluation/test_evaluation_config.py -v
uv run pytest tests/unit/evaluation/test_evaluation_run.py -v
uv run pytest tests/unit/evaluation/test_evaluator.py -v
uv run pytest tests/unit/evaluation/test_evaluation_orchestrator.py -v   # extended for R3's thresholds override
uv run pytest tests/integration/test_evaluator_flow_integration.py -v -m integration
uv run pytest --cov=deepeval_platform --cov-report=term-missing --cov-fail-under=80
```

## Automated coverage

| Requirement | Automated test scope |
|---|---|
| Full pipeline, happy path (US1) | Given known traces for a bot/period, `start()` produces a run that reaches `COMPLETED` with one `EvaluationResult` per trace, via a stub `ResultPublisher` that records what it published |
| Exhaustive collection beyond M2.1 cap (FR-004) | Repository responses spanning multiple pages and an evaluator run with more than 500 traces return/process every matching trace exactly once; existing `TraceCollector.collect()` still returns only the most recent 500 |
| Duplicate trace identity (FR-006/FR-010) | Repeated source outcomes for one `trace_id` become one extraction error and no result for that ID; unique IDs still produce exactly one result and no result-map overwrite occurs |
| Missing trace identity (FR-010) | An empty/whitespace-only trace ID invalidates exhaustive collection and reaches `UNABLE_TO_RUN`; no synthetic ID is created |
| Defensive pagination (FR-004) | Repeated pages, changing totals, malformed metadata, or premature empty pages raise `TraceRepositoryError` without looping or returning partial data |
| Zero-trace period (US1 Scenario 2) | Empty extraction publishes exactly one empty detached mapping, then reaches `COMPLETED`, with `total == 0`, `progress == 1.0`, and no error |
| Independent concurrent runs (US1 Scenario 3) | Two `start()` calls for different bots/periods get distinct `run.id`s and independently correct terminal state, run concurrently (e.g. asserted via a slow stub collector and overlapping thread lifetimes) |
| Cross-run lock isolation (FR-012) | Blocking one run in delivery/retry does not block state updates or coherent reads for another run |
| Immediate handle + async update (US2 Scenario 4, FR-003) | `start()` returns before the stubbed pipeline finishes; polling the same object's `status`/`processed` afterward observes it change without a second call |
| Progress semantics (US2, FR-008) | `total is None` before extraction completes; `processed`/`total` update per trace; `progress` is `None` while indeterminate and `processed/total` (or `1.0` for zero traces) after |
| Coherent concurrent state (FR-003/FR-008/FR-012) | Repeated `run.snapshot()` calls during worker updates remain internally consistent and monotonic; no snapshot combines status, counts, progress, timestamps, errors, or results from different transitions |
| Observer-visible delivery state (FR-007/FR-011) | A blocked initial observer sees `run.status == DELIVERING`, while `run.wait(short_timeout)` remains `False` and `end_timestamp` remains unset; success/failure then selects the appropriate terminal state |
| Final state includes timestamps (US2 Scenario 3, FR-009) | `run.wait(timeout)` returns `True`; `start_timestamp` is set at creation; `end_timestamp` is `None` until a terminal status, then set exactly once |
| Unexpected worker failure reaches final state (FR-011) | A non-trace-specific worker error yields `UNABLE_TO_RUN`; `run.wait(timeout)` returns `True`, `end_timestamp` is set, and `failure_message` is sanitized |
| Worker-start failure reaches final state (FR-011) | Failure while creating/starting the background thread after run creation transitions that run to `UNABLE_TO_RUN`, sets/sanitizes its failure state, and never leaves `STARTED` behind |
| Isolated per-trace failure (US3, FR-010) | One trace raises during normalization and another during evaluation; both are isolated, with `normalization_failed` and `evaluation_failed` respectively, and every other trace still has an `EvaluationResult` |
| Clean vs. failed distinguishable (US3 Scenario 2, FR-011) | A run with zero `PerTraceError`s reaches `COMPLETED`; a run with one or more reaches `COMPLETED_WITH_FAILURES`, and the two are asserted as distinct enum values |
| Invalid config rejected before run state exists (Edge Cases, FR-002/014/015) | Out-of-range threshold, non-later `period_end`, unknown metric, and unknown `bot_id` each raise before any `EvaluationRun` is constructed — assert no run object is ever produced (not even discarded) |
| Strict metric-entry structure (FR-015) | Mappings, tuples, arbitrary look-alike objects, malformed constructor calls, and duplicate `MetricThreshold` names are rejected without creating a run |
| Bot lookup error classification (FR-002) | An explicit missing-key/empty bot type becomes `UnknownBotError`; configuration parsing/loading and other `ConfigError` failures propagate unchanged |
| Identifier and period input domain (FR-002/FR-014) | Empty/whitespace bot IDs and metric names are rejected; naive datetimes mean UTC, aware datetimes are converted, and non-datetime boundaries raise `TypeError` |
| Threshold runtime domain (FR-002) | `0`, `1`, and finite in-range floats are accepted; below/above-range values, `NaN`, infinities, booleans, numeric strings, and arbitrary objects raise `InvalidThresholdError` without constructing a run or coercing input |
| Extraction-unreachable vs. per-trace failure (Edge Cases, FR-011) | Stub `TraceCollector.collect_all` raising once yields `UNABLE_TO_RUN`; a per-trace exception after extraction succeeds yields `COMPLETED_WITH_FAILURES` — the two paths are asserted as reaching different statuses |
| Delivery failure + retained results (Edge Cases, FR-007, SC-006) | A `ResultPublisher.publish` that raises once yields `DELIVERY_FAILED` with completed results available through the read-only `run.results` interface |
| Observer mutation isolation (FR-007) | An observer cannot add/remove result keys, and mutating a nested metric object from its detached snapshot before raising does not alter `run.results` or the fresh snapshot supplied to retry |
| Retry semantics (Edge Cases, FR-007, SC-007) | Retry after a successful second `publish` transitions to `COMPLETED`/`COMPLETED_WITH_FAILURES` per the original trace outcome, and asserts `publish` was called exactly twice total with no new extraction/normalization/evaluation calls recorded |
| Retry rejected on wrong status | `retry_delivery()` on a `COMPLETED`/`IN_PROGRESS`/`DELIVERING`/`UNABLE_TO_RUN` run raises `InvalidRetryStateError` and leaves `run.status` unchanged |
| Retry rejection is side-effect free | A rejected retry leaves the complete coherent run snapshot and completion signaling unchanged |
| Retry serialization | Two concurrent `retry_delivery()` calls on the same `DELIVERY_FAILED` run: one proceeds, the other raises `RetryInProgressError` immediately without waiting for the first to finish |
| Threshold override, not bot default mutation (FR-013) | A run with an overridden threshold produces a `MetricResult` scored against the override; a fresh, separate call to `EvaluationOrchestrator.evaluate()` without an override for the same bot still resolves the original `bots.yaml` threshold afterward |
| Sanitized per-trace errors | A `PerTraceError.message` built from an exception containing a bearer token/opaque credential has it redacted, reusing the existing `sanitize_error()` test fixtures/assertions from M3.1 |
| Sanitized whole-run errors (FR-011) | Extraction, worker, and worker-start failures containing raw exception text and credentials produce only a stable redacted `failure_message` |
| Metric-level vs. trace-level failure (FR-006) | A returned `EvaluationResult` containing supported metric-level errors remains a trace result; only an orchestrator exception creates `evaluation_failed` |

Unit tests stub `TraceCollector`, `TraceNormalizer`, `EvaluationOrchestrator`, and `ResultPublisher`
at the `Evaluator` boundary — no real Langfuse/LLM call is required to prove orchestration
correctness. The one `-m integration` test exercises the real composition
(`TraceRepository` → `TraceCollector.collect_all()` → `TraceNormalizer` →
`EvaluationOrchestrator` → `ResultPublisher` → observer) against an in-process HTTP server serving
deterministic paginated Langfuse responses. A deterministic `DeepEvalBaseLLM` fake replaces only
the external judge-model call. The test reads no `.env` credentials, performs no external network
request, contains no `skip`/`skipif`, and MUST pass in the normal local/CI test environment.

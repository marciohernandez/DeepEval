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
| Full pipeline, happy path (US1) | Given known traces for a bot/period, `start()` produces a run that reaches `COMPLETED` with one `EvaluationResult` per trace, via a stub `ResultHandoff` that records what it received |
| Zero-trace period (US1 Scenario 2) | Empty extraction still reaches `COMPLETED`, `total == 0`, `progress == 1.0`, no error |
| Independent concurrent runs (US1 Scenario 3) | Two `start()` calls for different bots/periods get distinct `run.id`s and independently correct terminal state, run concurrently (e.g. asserted via a slow stub collector and overlapping thread lifetimes) |
| Immediate handle + async update (US2 Scenario 4, FR-003) | `start()` returns before the stubbed pipeline finishes; polling the same object's `status`/`processed` afterward observes it change without a second call |
| Progress semantics (US2, FR-008) | `total is None` before extraction completes; `processed`/`total` update per trace; `progress` is `None` while indeterminate and `processed/total` (or `1.0` for zero traces) after |
| Final state includes timestamps (US2 Scenario 3, FR-009) | `start_timestamp` set at creation; `end_timestamp` is `None` until a terminal status, then set exactly once |
| Isolated per-trace failure (US3, FR-010) | One trace raises during normalization and another during evaluation; both are isolated, both appear in `run.errors` with `trace_id`/`stage`/`error_code`/`message`, and every other trace still has an `EvaluationResult` |
| Clean vs. failed distinguishable (US3 Scenario 2, FR-011) | A run with zero `PerTraceError`s reaches `COMPLETED`; a run with one or more reaches `COMPLETED_WITH_FAILURES`, and the two are asserted as distinct enum values |
| Invalid config rejected before run state exists (Edge Cases, FR-002/014/015) | Out-of-range threshold, non-later `period_end`, unknown metric, and unknown `bot_id` each raise before any `EvaluationRun` is constructed — assert no run object is ever produced (not even discarded) |
| Extraction-unreachable vs. per-trace failure (Edge Cases, FR-011) | Stub `TraceCollector.collect` raising once yields `UNABLE_TO_RUN`; a per-trace exception after extraction succeeds yields `COMPLETED_WITH_FAILURES` — the two paths are asserted as reaching different statuses |
| Delivery failure + retained results (Edge Cases, FR-007, SC-006) | A `ResultHandoff.deliver` that raises once yields `DELIVERY_FAILED` with `run._results` populated and inspectable |
| Retry semantics (Edge Cases, FR-007, SC-007) | Retry after a successful second `deliver` transitions to `COMPLETED`/`COMPLETED_WITH_FAILURES` per the original trace outcome, and asserts `deliver` was called exactly twice total with no new extraction/normalization/evaluation calls recorded |
| Retry rejected on wrong status | `retry_delivery()` on a `COMPLETED`/`IN_PROGRESS`/`UNABLE_TO_RUN` run raises `InvalidRetryStateError` and leaves `run.status` unchanged |
| Retry serialization | Two concurrent `retry_delivery()` calls on the same `DELIVERY_FAILED` run: one proceeds, the other raises `RetryInProgressError` immediately without waiting for the first to finish |
| Threshold override, not bot default mutation (FR-013) | A run with an overridden threshold produces a `MetricResult` scored against the override; a fresh, separate call to `EvaluationOrchestrator.evaluate()` without an override for the same bot still resolves the original `bots.yaml` threshold afterward |
| Sanitized per-trace errors | A `PerTraceError.message` built from an exception containing a bearer token/opaque credential has it redacted, reusing the existing `sanitize_error()` test fixtures/assertions from M3.1 |

Unit tests stub `TraceCollector`, `TraceNormalizer`, `EvaluationOrchestrator`, and `ResultHandoff`
at the `Evaluator` boundary — no real Langfuse/LLM call is required to prove orchestration
correctness. The one `-m integration` test exercises the real composition
(`TraceCollector` → `TraceNormalizer` → `EvaluationOrchestrator`) against local fixtures/a stub
Langfuse response, following the same skip-with-reason convention as M4.1's integration suite when
live credentials are absent.

# Implementation Plan: Evaluator Principal

**Branch**: `009-evaluator-principal` | **Date**: 2026-07-16 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/009-evaluator-principal/spec.md`

## Summary

M4.2 adds `deepeval_platform/evaluation/evaluator.py` — a facade orchestrating one full
extract-normalize-evaluate-handoff run for a bot/period, on top of the already-implemented M2.1
`TraceCollector`, M2.2 `TraceNormalizer`, and M3.1 `EvaluationOrchestrator`. `EvaluationConfig`
(`evaluation/evaluation_config.py`) models a run's inputs with `metric_thresholds: dict[str,
float]` — a single field that structurally guarantees FR-015's one-metric-one-threshold,
no-duplicates rule instead of needing cross-validation code (research.md R1). `Evaluator.start()`
validates synchronously (unknown metric, out-of-range threshold, unknown bot, invalid period — no
partial state on failure), creates an `EvaluationRun` (`evaluation/evaluation_run.py`, UUID-keyed,
mutable, holding `status: RunStatus`/`processed`/`total`/`errors`/timestamps), and returns it
immediately while a background `threading.Thread` mutates that same object as it works (research.md
R2) — there is no server-side run registry or `get_run(id)` API; the object the caller already
holds *is* the queryable state (research.md R6). Per-trace failures during normalization or
evaluation become isolated `PerTraceError` entries and never stop the remaining traces (FR-010); a
whole-run setup/extraction failure routes to `UNABLE_TO_RUN` instead. `EvaluationOrchestrator.
evaluate()` gains an additive, optional `thresholds` override parameter so a run's config can
override a bot's `bots.yaml` defaults for that run only, without `Evaluator` duplicating the
orchestrator's threshold/timeout/judge resolution (research.md R3). Completed results are handed
off through a new `ResultHandoff` interface (`evaluation/result_handoff.py`) — this milestone
defines the interface only, per the spec's explicit scope boundary; a failed handoff transitions
the run to `DELIVERY_FAILED` while retaining its in-memory results on the run object itself, and
`Evaluator.retry_delivery(run)` repeats only the handoff, serialized per-run via a lock stored on
the run (research.md R6).

## Technical Context

**Language/Version**: Python 3.13 in this repository; constitution minimum Python `^3.11`.

**Primary Dependencies**:
- Existing `deepeval_platform.collection.trace_collector.TraceCollector` (M2.1) for extraction —
  unchanged.
- Existing `deepeval_platform.normalization.trace_normalizer.TraceNormalizer` (M2.2) for
  per-trace normalization — unchanged.
- Existing `deepeval_platform.evaluation.evaluation_orchestrator.EvaluationOrchestrator` (M3.1)
  for per-trace metric evaluation — extended with one additive optional parameter (research.md
  R3), no breaking change to its existing signature/tests.
- Existing `deepeval_platform.evaluation.metrics.metric_factory.MetricFactory` (`_registry`) for
  metric-name validation, reusing the exact check `EvaluationOrchestrator` already performs.
- Existing `deepeval_platform.config.config_manager.ConfigManager` — sole config reader, used only
  for the `bots.{bot_id}.bot_type` existence check.
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
`EvaluationOrchestrator`, and `ResultHandoff` at the `Evaluator` boundary. One `-m integration`
test exercises the real M2.1→M2.2→M3.1 composition against local/stub fixtures, following the
skip-with-reason convention already used by the M4.1 integration suite when live credentials are
absent.

**Constraints**:
- No partial `EvaluationRun` state is ever created for an invalid `EvaluationConfig` (FR-002).
- `bots.yaml` is never mutated by a run's threshold overrides (FR-013).
- A per-trace failure never stops the remaining traces in the run (FR-010, SC-002).
- `start()` returns before processing completes; the returned object is later mutated in place,
  never replaced (FR-003, US2 Scenario 4).
- At most one retry attempt executes per run at a time (FR-007 last clause).
- No raw exception/credential text reaches `PerTraceError.message` (reuses `sanitize_error()`).

**Scale/Scope**: 1 new domain package addition (files, not a new top-level package —
`deepeval_platform/evaluation/` already exists): `evaluation_config.py`, `evaluation_run.py`
(`EvaluationRun`, `RunStatus`, `PerTraceError`), `evaluator.py`, `result_handoff.py`; one additive
parameter on the existing `EvaluationOrchestrator.evaluate()`; four new exception classes appended
to the existing `evaluation/errors.py` (`UnknownBotError`, `InvalidPeriodError`,
`InvalidRetryStateError`, `RetryInProgressError`) plus reuse of three existing ones
(`EmptyMetricListError`, `UnknownMetricError`, `InvalidThresholdError`). No new migration, no new
config schema, no new runtime dependency.

## Constitution Check

*GATE: Re-checked against constitution v1.4.0.*

| Principle | Check | Status |
|---|---|---|
| I. OOP-First | `EvaluationConfig` (passive value object), `EvaluationRun`/`RunStatus`/`PerTraceError` (run state), `ResultHandoff` (ABC, single method), and `Evaluator` (orchestration only, delegates extraction/normalization/evaluation to their existing owners) each have one responsibility; no new monolithic file. | PASS |
| II. DeepEval-First | No DeepEval native class is a candidate here — `Evaluator` is a project-local orchestration abstraction over already-DeepEval-first collaborators (`EvaluationOrchestrator`/`MetricFactory`, M3.1), exactly like `TraceExtractor`/`EvaluationStrategy` are exempted project-local adapters under Principle II's second clause. | PASS |
| III. LangChain-First | Not applicable — this milestone orchestrates the evaluator's own pipeline, not a bot-under-evaluation integration (explicit scope boundary in Principle III). | N/A |
| IV. TDD | Every new class/behavior gets a test written and observed RED before its implementation; coverage stays >=80% (quickstart.md enumerates the required scenarios). | PASS (process gate, verified at implementation) |
| V. Zero Hardcode | No new credential/config value; the one config read (`bots.{bot_id}.bot_type`) goes through `ConfigManager`, the sole reader. | PASS |
| VI. Extensibility | `ResultHandoff` is injected (constructor parameter), matching the project's existing dependency-injection convention (`SyntheticDatasetGenerator`, `EvaluationOrchestrator`); a new handoff implementation requires zero `Evaluator` changes. No Factory/Strategy/Observer/Repository pattern is warranted here — there is exactly one implementation to select (`Evaluator` itself), not a family DeepEval or bot-type extension needs to grow. | PASS |

No design-pattern exception is requested. Constitution v1.4.0 is in force. All principle checks
pass; no implementation blocker remains.

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
    ├── evaluation_run.py        # NEW — EvaluationRun, RunStatus, PerTraceError
    ├── result_handoff.py        # NEW — ResultHandoff ABC
    ├── evaluator.py              # NEW — Evaluator (the orchestrator)
    ├── errors.py                  # MODIFIED — UnknownBotError, InvalidPeriodError,
    │                              #   InvalidRetryStateError, RetryInProgressError added
    └── evaluation_orchestrator.py # MODIFIED — evaluate() gains optional `thresholds` param
tests/
├── unit/evaluation/
│   ├── test_evaluation_config.py    # NEW
│   ├── test_evaluation_run.py        # NEW
│   ├── test_evaluator.py             # NEW
│   └── test_evaluation_orchestrator.py  # MODIFIED — threshold-override coverage added
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

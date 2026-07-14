# Implementation Plan: HallucinationMetric + TaskCompletionMetric Integration

**Branch**: `005-rag-agentic-metrics` | **Date**: 2026-07-14 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/005-rag-agentic-metrics/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command. See `.specify/templates/plan-template.md` for the execution workflow.

## Summary

M3.2 closes the two metric names left unregistered by M3.1: `task_completion` (already declared
by `AgentStrategy.get_metrics()` since M2.1, but unresolvable today — every agentic-bot
evaluation fails before producing a result) and `hallucination` (not yet referenced by any
strategy; this milestone adds it to `RAGStrategy.get_metrics()` so it runs automatically on every
RAG bot). Both are plain `MetricBase` subclasses wrapping DeepEval's native
`TaskCompletionMetric` and `HallucinationMetric` (Principle II), registered via the same
`@MetricFactory.register(name)` decorator pattern as the six M3.1 wrappers — zero changes to
`MetricBase`, `MetricFactory`, `EvaluationContext`, `EvaluationResult`, or
`EvaluationOrchestrator`. The one wrinkle: DeepEval's native `HallucinationMetric` requires
`LLMTestCase.context` (`SingleTurnParams.CONTEXT`), a field `MetricBase._build_test_case` does not
populate (it only fills `retrieval_context` from `NormalizedTrace.context`) — so
`HallucinationMetricWrapper` overrides test-case construction locally, scoped to itself only
(FR-007). `TaskCompletionMetricWrapper` needs no override: DeepEval's native metric only requires
`input`/`actual_output` (verified against the installed package — `_trace_dict` is absent from
this project's `LLMTestCase` construction, so it falls back to its documented
input/output/tools_called path), both already populated by the shared base.

## Technical Context

**Language/Version**: Python 3.13 (pinned via `.python-version`), minimum runtime `^3.11` per
constitution.

**Primary Dependencies**:
- `deepeval ^4.0.6` — `HallucinationMetric`, `TaskCompletionMetric` (both verified present and
  importable from `deepeval.metrics` in the installed package), `LLMTestCase`, `BaseMetric`.
- `deepeval_platform.evaluation.metrics.{metric_base,metric_factory}` (M3.1) — unchanged, reused
  as-is. `MetricBase._build_test_case` is not modified; `HallucinationMetricWrapper` overrides
  test-case construction only within its own subclass.
- `deepeval_platform.evaluation.strategies.rag_strategy.RAGStrategy` (M2.1) — one-line change:
  `get_metrics()` gains `"hallucination"` as a sixth entry.
- `deepeval_platform.evaluation.strategies.agent_strategy.AgentStrategy` (M2.1) — unchanged;
  already declares `"task_completion"`, this feature only makes that name resolvable.
- `deepeval_platform.normalization.models.NormalizedTrace` (M2.2) — unchanged, frozen this
  milestone (spec Assumptions); `HallucinationMetricWrapper` reads the same `trace.context` field
  the shared base already reads for `retrieval_context`, just also maps it to `context`.

**Storage**: N/A — no change to M3.1's in-memory-only scope.

**Testing**: `pytest`, `pytest-asyncio`, `pytest-mock`, `pytest-cov` with the project's existing
`--cov-fail-under=80` gate (Principle IV, NON-NEGOTIABLE TDD — tests precede implementation).

**Target Platform**: Linux server — same backend process as the rest of `deepeval_platform/`.

**Project Type**: Single project (existing `deepeval_platform/` package + `tests/`), no new
top-level project.

**Performance Goals**: No new target — both wrappers run inside the same concurrent
`asyncio.gather()` + per-metric `asyncio.wait_for()` orchestration already established in M3.1;
nothing here changes that mechanism.

**Constraints**: Threshold/timeout resolution for `hallucination` and `task_completion` follows
the exact same `ConfigManager`-based path already generic in `EvaluationOrchestrator` — no new
config keys are structurally required (native defaults apply until/unless an operator adds
`bots.<id>.metrics.hallucination.threshold` etc. to `bots.yaml`, which requires no code change
per M3.1's existing config schema).

**Scale/Scope**: 2 new concrete `MetricBase` wrappers (`hallucination`, `task_completion`), 1
one-line addition to `RAGStrategy.get_metrics()`. No new config keys, no new `.env` keys, no
schema/interface change to any M3.1 component.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Check | Status |
|---|---|---|
| I. OOP-First | Two more single-responsibility `MetricBase` subclasses under `deepeval_platform/evaluation/metrics/native/`, same pattern as the six M3.1 wrappers; `HallucinationMetricWrapper`'s local override is the minimal polymorphic extension point (`_build_test_case` overridden in the subclass only, not the base) | PASS |
| II. DeepEval-First | Both wrappers delegate 100% of scoring to DeepEval's native `HallucinationMetric`/`TaskCompletionMetric` via `a_measure()`; no scoring logic reimplemented. Native constructors and required-params verified directly against the installed package before writing any code | PASS |
| III. LangChain-First | N/A — evaluation-domain modules are explicitly out of this principle's scope per its own text | N/A |
| IV. TDD (NON-NEGOTIABLE) | Tests written first for both wrappers and the `RAGStrategy` change; ≥80% coverage enforced by existing `pytest-cov` config | PASS (process gate, enforced during `/speckit-tasks` + `/speckit-implement`) |
| V. Zero Hardcode | No new credentials or config keys; threshold/timeout resolution reuses M3.1's existing `ConfigManager`-based mechanism untouched | PASS |
| VI. Design Patterns | Both wrappers self-register via the existing `MetricFactory.create(name)` Factory Method — zero changes to the factory itself, satisfying "adding a metric requires only a new subclass" | PASS |

No violations — Complexity Tracking table is not needed.

## Project Structure

### Documentation (this feature)

```text
specs/005-rag-agentic-metrics/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md         # Phase 1 output (/speckit-plan command)
├── quickstart.md        # Phase 1 output (/speckit-plan command)
└── tasks.md             # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

No `contracts/` directory this feature: FR-005 requires zero change to the Python API surface
already documented in `specs/004-metric-factory-eval-strategy/contracts/evaluation-api.md`
(`MetricFactory`, `MetricBase`, `EvaluationOrchestrator` signatures are all unchanged) — that
contract remains authoritative, extended only by two more valid values for `metric_names` entries
and `MetricFactory.create()`'s `name` argument.

### Source Code (repository root)

```text
deepeval_platform/
└── evaluation/
    ├── strategies/
    │   └── rag_strategy.py                 # MODIFIED — get_metrics() gains "hallucination"
    └── metrics/
        └── native/
            ├── __init__.py                 # MODIFIED — imports the two new wrapper modules
            ├── hallucination_metric.py     # NEW — HallucinationMetricWrapper
            └── task_completion_metric.py   # NEW — TaskCompletionMetricWrapper

tests/
└── unit/evaluation/
    ├── test_rag_strategy.py                        # MODIFIED — asserts "hallucination" present
    └── metrics/native/
        ├── test_hallucination_metric.py             # NEW
        └── test_task_completion_metric.py           # NEW
```

**Structure Decision**: Single project, extending the existing `deepeval_platform/evaluation/`
domain package in place — same `metrics/native/` sub-package M3.1 already established, no new
top-level project, no new sub-package.

## Complexity Tracking

*No violations — table intentionally left empty.*

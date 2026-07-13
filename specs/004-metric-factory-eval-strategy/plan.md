# Implementation Plan: MetricFactory + EvaluationStrategy Integration

**Branch**: `004-metric-factory-eval-strategy` | **Date**: 2026-07-13 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/004-metric-factory-eval-strategy/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command. See `.specify/templates/plan-template.md` for the execution workflow.

## Summary

M3.1 turns the metric *names* that `EvaluationStrategy.get_metrics()` (M2.1) already returns into
concrete scores. It adds: `MetricBase` (ABC wrapping one native DeepEval `BaseMetric` subclass
each), `MetricFactory` (Factory Method registry, self-registration via decorator),
`EvaluationContext` (per-trace input: `NormalizedTrace` + resolved threshold map),
`MetricResult` + `EvaluationResult` (per-metric and aggregated output, `EvaluationResult` kept
distinct from the persisted `deepeval_platform.repositories.models.EvaluationResult` of M1), and
a new `EvaluationOrchestrator` that resolves thresholds/timeouts via `ConfigManager`, validates
the metric-name list, runs every `measure()` concurrently (`asyncio.gather` + per-metric
`asyncio.wait_for`), and aggregates with AND-semantics and per-metric failure isolation. All
scoring logic is delegated to DeepEval's native metrics (`AnswerRelevancyMetric`,
`FaithfulnessMetric`, `ContextualPrecisionMetric`, `ContextualRecallMetric`,
`ContextualRelevancyMetric`, `ToolCorrectnessMetric`) per Principle II — nothing here
reimplements scoring.

## Technical Context

**Language/Version**: Python 3.13 (pinned via `.python-version`), minimum runtime `^3.11` per
constitution.

**Primary Dependencies**:
- `deepeval ^4.0.6` — `BaseMetric`, `LLMTestCase`, `ToolCall`, `AnswerRelevancyMetric`,
  `FaithfulnessMetric`, `ContextualPrecisionMetric`, `ContextualRecallMetric`,
  `ContextualRelevancyMetric`, `ToolCorrectnessMetric`, `DeepEvalBaseLLM`.
- `deepeval_platform.llm` (M1) — `LLMProviderFactory.create(provider, model)` →
  `LLMProviderBase.as_deepeval_model() -> DeepEvalBaseLLM`, used as the judge model passed into
  every native metric constructor. `LLMProviderBase` is never subclassed or reimplemented here;
  `GPTModel`/`AnthropicModel`/`OpenRouterModel` are never instantiated directly by this feature.
- `deepeval_platform.config.ConfigManager` (M1, Singleton) — sole reader of `bots.yaml` /
  `settings.yaml` for thresholds, timeouts, and judge provider/model.
- `deepeval_platform.evaluation.{bot_type,strategy_base,strategy_factory}` (M2.1) — unchanged;
  `EvaluationStrategyBase.get_metrics()` remains the sole source of canonical metric-name lists.
- `deepeval_platform.normalization.models.NormalizedTrace` (M2.2) — unchanged; consumed read-only.
- stdlib: `abc`, `dataclasses`, `asyncio`, `re`, `logging`.

**Storage**: N/A — this milestone produces `EvaluationResult` in memory only. Persistence
(`EvaluationRepository`, already scaffolded in M1 for a *different*, per-metric-row shape) is
explicitly out of scope (spec Assumptions).

**Testing**: `pytest ^9`, `pytest-asyncio` (async `measure()`/orchestrator), `pytest-mock`,
`pytest-cov` with the project's existing `--cov-fail-under=80` gate (Principle IV, NON-NEGOTIABLE
TDD — tests precede implementation for every module below).

**Target Platform**: Linux server — same backend process as the rest of `deepeval_platform/`.

**Project Type**: Single project (existing `deepeval_platform/` package + `tests/`), no new
top-level project.

**Performance Goals**: No new explicit throughput target. `measure()` calls for one trace run
concurrently (FR-014) to cut wall-clock latency versus sequential judge-LLM round-trips; no
concurrency cap this milestone (Clarifications).

**Constraints**: Per-metric timeout, configurable (global default + optional per-metric
override), no retry (FR-015/FR-011); zero hardcoded thresholds/timeouts/judge selection — all via
`ConfigManager` reading `config/bots.yaml` / `config/settings.yaml` (Principle V).

**Scale/Scope**: 6 concrete `MetricBase` wrappers (5 RAG metrics + `tool_correctness`),
`MetricBase`, `MetricFactory`, `EvaluationContext`, `MetricResult`, `EvaluationResult`,
`EvaluationOrchestrator`, a small shared-errors module, and two YAML config extensions (no new
`.env` keys — no new credentials introduced).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Check | Status |
|---|---|---|
| I. OOP-First | `MetricBase` ABC + one subclass per native metric (polymorphism); `MetricFactory`, `EvaluationContext`, `EvaluationResult`/`MetricResult`, `EvaluationOrchestrator` each single-responsibility, organized under `deepeval_platform/evaluation/` | PASS |
| II. DeepEval-First | Every concrete metric wraps exactly one native `BaseMetric` subclass and delegates `measure`/scoring to it (`a_measure`); no scoring logic reimplemented; insufficient-input handling reuses DeepEval's own `MissingTestCaseParamsError` rather than duplicating `ValidationRule` (M2.2) | PASS |
| III. LangChain-First | N/A — evaluation-domain modules are explicitly out of this principle's scope per its own text | N/A |
| IV. TDD (NON-NEGOTIABLE) | Tests written first for every new module; ≥80% coverage enforced by existing `pytest-cov` config | PASS (process gate, enforced during `/speckit-tasks` + `/speckit-implement`) |
| V. Zero Hardcode | Thresholds/timeouts/judge provider read via `ConfigManager` from `bots.yaml`/`settings.yaml`; no credentials added, `.env.example` unchanged | PASS |
| VI. Design Patterns | `MetricFactory.create(name)` is exactly the Factory Method the constitution's own table names | PASS |

No violations — Complexity Tracking table is not needed.

## Project Structure

### Documentation (this feature)

```text
specs/004-metric-factory-eval-strategy/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md        # Phase 1 output (/speckit-plan command)
├── quickstart.md        # Phase 1 output (/speckit-plan command)
├── contracts/
│   └── evaluation-api.md   # Phase 1 output (/speckit-plan command)
└── tasks.md             # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
deepeval_platform/
├── evaluation/
│   ├── bot_type.py                    # existing (M2.1) — unchanged
│   ├── strategy_base.py               # existing (M2.1) — unchanged
│   ├── strategy_factory.py            # existing (M2.1) — unchanged
│   ├── strategies/                    # existing (M2.1) — unchanged
│   ├── errors.py                      # NEW — shared exceptions + sanitize_error()
│   ├── evaluation_context.py          # NEW — EvaluationContext dataclass
│   ├── evaluation_result.py           # NEW — MetricResult + EvaluationResult dataclasses
│   ├── evaluation_orchestrator.py      # NEW — EvaluationOrchestrator
│   └── metrics/
│       ├── __init__.py                # NEW — imports native/ to trigger self-registration
│       ├── metric_base.py             # NEW — MetricBase ABC
│       ├── metric_factory.py          # NEW — MetricFactory registry
│       └── native/
│           ├── __init__.py            # NEW — imports every wrapper module below
│           ├── answer_relevancy_metric.py
│           ├── faithfulness_metric.py
│           ├── contextual_precision_metric.py
│           ├── contextual_recall_metric.py
│           ├── contextual_relevancy_metric.py
│           └── tool_correctness_metric.py
├── config/config_manager.py           # existing (M1) — unchanged (dotted-key flatten already
│                                       # supports the new nested keys below)
├── normalization/models.py            # existing (M2.2) — unchanged
├── repositories/models.py             # existing (M1) — unchanged; its EvaluationResult is a
│                                       # distinct, per-metric-row *persisted* shape (see research.md)
└── llm/{base,factory}.py              # existing (M1) — unchanged

config/
├── bots.yaml       # EXTENDED — new `metrics: {<name>: {threshold: <float>}}` map per bot
└── settings.yaml   # EXTENDED — new `evaluation:` section (timeouts + judge provider/model)

tests/
├── unit/evaluation/
│   ├── test_evaluation_context.py
│   ├── test_evaluation_result.py
│   ├── test_evaluation_orchestrator.py
│   ├── test_errors.py
│   └── metrics/
│       ├── test_metric_base.py
│       ├── test_metric_factory.py
│       ├── test_metric_factory_extensibility.py
│       └── native/
│           ├── test_answer_relevancy_metric.py
│           ├── test_faithfulness_metric.py
│           ├── test_contextual_precision_metric.py
│           ├── test_contextual_recall_metric.py
│           ├── test_contextual_relevancy_metric.py
│           └── test_tool_correctness_metric.py
└── integration/
    └── test_evaluation_orchestrator_integration.py
```

**Structure Decision**: Single project, extending the existing `deepeval_platform/evaluation/`
domain package in place — no new top-level project. `metrics/` is a new sub-package (mirrors the
existing `strategies/` and `normalization/validation/rules/` sub-package pattern already used for
per-item extensibility in this repo).

## Complexity Tracking

*No violations — table intentionally left empty.*

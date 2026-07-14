# Implementation Plan: Quality/Safety + Conversational Metrics Integration

**Branch**: `006-quality-conversational-metrics` | **Date**: 2026-07-14 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/006-quality-conversational-metrics/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command. See `.specify/templates/plan-template.md` for the execution workflow.

## Summary

M3.3 closes the two names `ConversationStrategy.get_metrics()` has declared but never resolved
since M2.1 (`conversation_completeness`, `turn_relevancy` — same broken-path pattern `hallucination`
and `task_completion` fixed for RAG/Agent in M3.2), adds `bias`/`toxicity` as a cross-cutting safety
check to all three strategies, adds `knowledge_retention`/`role_adherence` to
`ConversationStrategy`, and registers (but does not auto-wire) four opt-in metrics —
`summarization`, `json_correctness`, `prompt_alignment`, `conversational_g_eval` — activated only
through new optional `config/bots.yaml` keys.

The one real design fork from M3.1/M3.2: five of these ten metrics are `ConversationalTestCase`-
based, and `MetricBase._build_test_case` only knows how to build an `LLMTestCase`. This milestone
adds a new sibling ABC, `ConversationalMetricBase` (structurally identical to `MetricBase` —
same `threshold`/`passed`/`measure()` surface — so `EvaluationOrchestrator` calls either kind of
wrapper polymorphically without change), which maps `NormalizedTrace.messages` into DeepEval `Turn`
objects. An invalid `Message.role` (anything but `user`/`assistant`) is rejected by `Turn`'s own
pydantic `Literal` field at construction time — no bespoke role-validation code is written; the
failure flows through the exact same generic per-metric isolation `EvaluationOrchestrator` has had
since M3.1.

The four opt-in metrics need per-bot parameters `NormalizedTrace` doesn't carry
(`expected_schema`, `prompt_instructions`, `criteria`) plus `role_adherence` needs an optional
`chatbot_role` — all four sourced from new optional `bots.yaml` keys via a new
`BotMetricConfigResolver` (config-domain only, no metric logic) and forwarded through one
backward-compatible generalization of `MetricFactory.create()` (generic `**options`, no
if/else branching on metric name). One real gap found and closed in Phase 0: `ConfigManager`
today has no way to represent a YAML *list* value (`prompt_instructions`) — its flattener
stringifies non-dict values whole. Fixed by teaching `_flatten_yaml` to flatten lists into indexed
keys (`prompt_instructions.0`, `.1`, ...), reusing the exact flat-string-store mechanism every other
config value already goes through — no new `ConfigManager` method, no other reader of `bots.yaml`
introduced (Principle V unchanged).

## Technical Context

**Language/Version**: Python 3.13 (pinned via `.python-version`), minimum runtime `^3.11` per
constitution.

**Primary Dependencies**:
- `deepeval ^4.0.6` (installed: `4.0.7`) — `BiasMetric`, `ToxicityMetric`, `SummarizationMetric`,
  `JsonCorrectnessMetric`, `PromptAlignmentMetric`, `ConversationalGEval`,
  `KnowledgeRetentionMetric`, `RoleAdherenceMetric`, `ConversationCompletenessMetric`,
  `TurnRelevancyMetric` — all verified importable from `deepeval.metrics` and structurally
  documented in `research.md` §R1. `ConversationalTestCase`, `Turn` verified in `research.md` §R2.
- `deepeval_platform.evaluation.metrics.{metric_base,metric_factory}` (M3.1) — `MetricFactory.create()`
  gains generic `**options` (FR-016, `research.md` §R7); `MetricBase` itself is untouched.
- New: `deepeval_platform.evaluation.metrics.conversational_metric_base.ConversationalMetricBase`
  (FR-002, `research.md` §R8) — sibling ABC, not a subclass of `MetricBase`.
- New: `deepeval_platform.evaluation.bot_metric_config_resolver.BotMetricConfigResolver` (FR-015).
- `deepeval_platform.evaluation.strategies.{rag_strategy,agent_strategy,conversation_strategy}`
  (M2.1) — additive `get_metrics()` changes only (FR-006/FR-007/FR-008).
- `deepeval_platform.evaluation.evaluation_orchestrator.EvaluationOrchestrator` (M3.1) — internal-
  only change: resolves per-metric options via `BotMetricConfigResolver` and forwards them to
  `MetricFactory.create()`; public `evaluate(trace, bot_id, metric_names)` signature unchanged
  (FR-013, `research.md` §R3).
- `deepeval_platform.config.config_manager.ConfigManager` (M1) — `_flatten_yaml` gains a `list`
  branch (`research.md` §R4); `get`/`get_optional`/`get_typed` API surface unchanged.
- `deepeval_platform.normalization.models.NormalizedTrace` (M2.2) — unchanged; `messages` (already
  present since M2.2) is read for the first time by `ConversationalMetricBase`.

**Storage**: N/A — no change to M3.1's in-memory-only scope.

**Testing**: `pytest`, `pytest-asyncio`, `pytest-mock`, `pytest-cov` with the project's existing
`--cov-fail-under=80` gate (Principle IV, NON-NEGOTIABLE TDD — tests precede implementation).

**Target Platform**: Linux server — same backend process as the rest of `deepeval_platform/`.

**Project Type**: Single project (existing `deepeval_platform/` package + `tests/`), no new
top-level project.

**Performance Goals**: No new target — all ten wrappers run inside the same concurrent
`asyncio.gather()` + per-metric `asyncio.wait_for()` orchestration established in M3.1; nothing
here changes that mechanism.

**Constraints**: Threshold/timeout configuration for all ten new metrics follows the exact same
`ConfigManager`-based resolution and native-default fallback already generic in
`EvaluationOrchestrator` since M3.1 — no new mechanism for those two aspects. The four opt-in
metrics additionally require their own config key(s) to be present or they are excluded entirely
(FR-011) — never attempted, never erroring for their absence.

**Scale/Scope**: 10 new metric wrapper classes (5 `MetricBase` + 5 `ConversationalMetricBase`), 1
new sibling ABC (`ConversationalMetricBase`), 1 new resolver class (`BotMetricConfigResolver`), 1
one-line-per-strategy additive change to all three `EvaluationStrategyBase` subclasses, 1
backward-compatible generalization of `MetricFactory.create()`, 1 internal (signature-preserving)
change to `EvaluationOrchestrator`, 1 additive branch in `ConfigManager._flatten_yaml`, 5 new
optional `bots.yaml` keys.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Check | Status |
|---|---|---|
| I. OOP-First | Ten single-responsibility wrapper subclasses across two sibling ABCs, one new config-domain resolver class with a single responsibility (merge + option resolution, no metric logic) — matches the M3.1/M3.2 pattern exactly | PASS |
| II. DeepEval-First | All ten wrappers delegate 100% of scoring to native DeepEval classes via `a_measure()`; no scoring logic reimplemented. Invalid-role rejection reuses `Turn`'s own pydantic validation rather than reimplementing it (research.md §R2). Every native class/constructor verified against the installed package before writing this plan (research.md §R1) | PASS |
| III. LangChain-First | N/A — evaluation-domain modules are explicitly out of this principle's scope per its own text | N/A |
| IV. TDD (NON-NEGOTIABLE) | Tests written first for all ten wrappers, `ConversationalMetricBase`, `BotMetricConfigResolver`, and every modified strategy/factory/orchestrator/config-manager change; ≥80% coverage enforced by existing `pytest-cov` config | PASS (process gate, enforced during `/speckit-tasks` + `/speckit-implement`) |
| V. Zero Hardcode | No new credentials. New `bots.yaml` keys added to the existing `ConfigManager`-governed config surface; `BotMetricConfigResolver` reads exclusively through `ConfigManager` (never opens `bots.yaml` itself) — `ConfigManager` remains the sole reader | PASS |
| VI. Design Patterns | All ten wrappers self-register via the existing `MetricFactory.create(name)` Factory Method — zero if/else branches added to the factory (FR-016 explicitly requires this); `BotMetricConfigResolver` is a plain single-responsibility class, not a new pattern requiring a table entry | PASS |

No violations — Complexity Tracking table is not needed.

## Project Structure

### Documentation (this feature)

```text
specs/006-quality-conversational-metrics/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md        # Phase 1 output (/speckit-plan command)
├── quickstart.md        # Phase 1 output (/speckit-plan command)
├── contracts/
│   └── evaluation-api.md   # Phase 1 output — additions to the 004 contract (MetricFactory.create() generalization, ConversationalMetricBase, BotMetricConfigResolver, new bots.yaml keys)
└── tasks.md             # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
deepeval_platform/
├── config/
│   └── config_manager.py                       # MODIFIED — _flatten_yaml gains a list-value branch
└── evaluation/
    ├── bot_metric_config_resolver.py            # NEW — BotMetricConfigResolver
    ├── evaluation_orchestrator.py               # MODIFIED — resolves + forwards per-metric options (signature unchanged)
    ├── strategies/
    │   ├── rag_strategy.py                       # MODIFIED — get_metrics() gains "bias", "toxicity"
    │   ├── agent_strategy.py                      # MODIFIED — get_metrics() gains "bias", "toxicity"
    │   └── conversation_strategy.py               # MODIFIED — get_metrics() gains "bias", "toxicity", "knowledge_retention", "role_adherence"
    └── metrics/
        ├── metric_factory.py                     # MODIFIED — create() gains generic **options
        ├── conversational_metric_base.py         # NEW — ConversationalMetricBase (sibling to MetricBase)
        └── native/
            ├── __init__.py                       # MODIFIED — imports the ten new wrapper modules
            ├── bias_metric.py                     # NEW — BiasMetricWrapper
            ├── toxicity_metric.py                 # NEW — ToxicityMetricWrapper
            ├── summarization_metric.py            # NEW — SummarizationMetricWrapper
            ├── json_correctness_metric.py          # NEW — JsonCorrectnessMetricWrapper
            ├── prompt_alignment_metric.py          # NEW — PromptAlignmentMetricWrapper
            ├── conversation_completeness_metric.py # NEW — ConversationCompletenessMetricWrapper
            ├── conversation_relevancy_metric.py    # NEW — ConversationRelevancyMetricWrapper (wraps TurnRelevancyMetric, registers as "turn_relevancy")
            ├── knowledge_retention_metric.py        # NEW — KnowledgeRetentionMetricWrapper
            ├── role_adherence_metric.py             # NEW — RoleAdherenceMetricWrapper
            └── conversational_g_eval_metric.py      # NEW — ConversationalGEvalMetricWrapper

config/
└── bots.yaml                                    # MODIFIED — optional new keys per data-model.md (json_schema, prompt_instructions, conversational_geval_criteria, chatbot_role, metrics.summarization.enabled)

tests/
└── unit/
    ├── config/
    │   └── test_config_manager.py                       # MODIFIED — new cases for list-value flattening
    └── evaluation/
        ├── test_rag_strategy.py                          # MODIFIED — asserts "bias"/"toxicity" present
        ├── test_agent_strategy.py                         # MODIFIED — asserts "bias"/"toxicity" present
        ├── test_conversation_strategy.py                  # MODIFIED — asserts six-entry list
        ├── test_evaluation_orchestrator.py                # MODIFIED — new isolation cases (invalid role, missing chatbot_role, malformed opt-in config)
        ├── test_bot_metric_config_resolver.py              # NEW
        └── metrics/
            ├── test_metric_factory.py                     # MODIFIED — asserts **options forwarding
            ├── test_conversational_metric_base.py          # NEW
            └── native/
                ├── test_bias_metric.py                     # NEW
                ├── test_toxicity_metric.py                 # NEW
                ├── test_summarization_metric.py            # NEW
                ├── test_json_correctness_metric.py          # NEW
                ├── test_prompt_alignment_metric.py          # NEW
                ├── test_conversation_completeness_metric.py # NEW
                ├── test_conversation_relevancy_metric.py    # NEW
                ├── test_knowledge_retention_metric.py        # NEW
                ├── test_role_adherence_metric.py             # NEW
                └── test_conversational_g_eval_metric.py      # NEW
```

**Structure Decision**: Single project, extending the existing `deepeval_platform/evaluation/`
domain package in place — same `metrics/native/` sub-package M3.1/M3.2 already established, plus
one new sibling module (`conversational_metric_base.py`) at the same level as `metric_base.py`, and
one new top-level `evaluation/` module (`bot_metric_config_resolver.py`) alongside
`evaluation_orchestrator.py`. No new top-level project, no new sub-package.

## Complexity Tracking

*No violations — table intentionally left empty.*

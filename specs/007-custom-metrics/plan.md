# Implementation Plan: Custom Metrics Integration (GEval, DAG, Ragas)

**Branch**: `007-custom-metrics` | **Date**: 2026-07-15 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/007-custom-metrics/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command. See `.specify/templates/plan-template.md` for the execution workflow.

## Summary

M3.4 adds four new opt-in metric wrappers — `g_eval`, `dag`, `ragas_answer_correctness`,
`ragas_context_recall` — none auto-wired into any `EvaluationStrategy.get_metrics()`, following the
exact opt-in pattern M3.3 established for `summarization`/`json_correctness`/`prompt_alignment`/
`conversational_g_eval`. `GEvalMetricWrapper` and `DAGMetricWrapper` are `MetricBase` subclasses
(`LLMTestCase`-based, same as every M3.1-M3.3 single-turn wrapper); `RagasMetricWrapper` is also a
`MetricBase` subclass, parameterized at construction by which of the two Ragas metrics to compute;
it is not itself registered, but backs two thin subclasses (`_AnswerCorrectnessMetricWrapper`,
`_ContextRecallMetricWrapper`), each hardcoding its own `ragas_metric_name` and each registered
directly under its own canonical name — no `MetricFactory.register()`/`create()` signature change
needed, just two more ordinary registered subclasses.

Two real design gaps close in Phase 0. First, DeepEval's native `GEval.__init__` accepts
`evaluation_params=None` without error, but `measure()`/`a_measure()` raise `ValueError` at call
time if it's still `None` — unlike every existing single-criterion wrapper, `GEvalMetricWrapper`
must supply `evaluation_params` explicitly at construction (research.md §R1). Second, `dag_builder`
(FR-005) is the first per-bot config value `BotMetricConfigResolver` must *invoke* rather than use
as-is — the resolved `importlib`/`getattr` target is called with zero arguments to produce the
`DeepAcyclicGraph`, a one-branch divergence from the `json_schema` resolution `dag_builder`
otherwise mirrors exactly (research.md §R2).

`RagasMetricWrapper` is the one wrapper that cannot simply forward to a native DeepEval metric's
`a_measure()` (Principle II doesn't apply — Ragas is an external, non-DeepEval framework the spec
explicitly scopes to side-by-side comparison, not replacement). It overrides `measure()` directly:
builds a Ragas `SingleTurnSample` from the same `NormalizedTrace` fields `MetricBase._build_test_case`
already reads (`input`→`user_input`, `output`→`response`, `expected_output`→`reference`,
`context`→`retrieved_contexts`), scores it with the selected Ragas metric instance, and maps the
result into the same `MetricResult` contract every other wrapper produces — so
`EvaluationOrchestrator`'s per-metric isolation (timeout, exception → `MetricResult(score=None,
passed=False, error=...)`) covers it unchanged, including the "ragas not installed"/"ragas
misconfigured" edge cases (spec Edge Cases), which surface as an ordinary caught exception at
`measure()` time — no new import-guard mechanism needed. Ragas' LLM/embeddings interfaces are
adapted from the bot's already-configured `DeepEvalBaseLLM` judge and the project's global
`embedding.model`/`embedding.dimensions` respectively (FR-009, FR-014) via one new adapter class
(`RagasLLMAdapter`) and the same `OpenAIEmbeddings(model=..., api_key=...)` construction
`QdrantVectorStoreProvider` already uses — no new configuration path, no `LangchainLLMWrapper`
(Principle III scopes LangChain to bot orchestration, not the evaluator's own judge-model wiring).

## Technical Context

**Language/Version**: Python 3.13 (pinned via `.python-version`), minimum runtime `^3.11` per
constitution.

**Primary Dependencies**:
- `deepeval ^4.0.6` (installed: `4.0.7`) — `GEval`, `DAGMetric` (+ `DeepAcyclicGraph` and node
  classes from `deepeval.metrics.dag`) verified importable and structurally documented in
  research.md §R1/§R2.
- New: `ragas >=0.2.0` — `SingleTurnSample`, `AnswerCorrectness`/`answer_correctness`,
  `ContextRecall`/`context_recall`, `BaseRagasLLM`, embeddings wrapper base — documented in
  research.md §R3. Not yet installed in this environment; added to `pyproject.toml` in this
  feature, installed during `/speckit-implement`.
- `deepeval_platform.evaluation.metrics.{metric_base,metric_factory}` (M3.1) — unchanged;
  `GEvalMetricWrapper`/`DAGMetricWrapper` extend `MetricBase` the same way
  `JsonCorrectnessMetricWrapper`/`ConversationalGEvalMetricWrapper` already do (custom `__init__`,
  no factory change). `RagasMetricWrapper` also extends `MetricBase` but overrides `measure()`
  (research.md §R4) since it has no native DeepEval class to delegate to.
- `deepeval_platform.evaluation.bot_metric_config_resolver.BotMetricConfigResolver` (M3.3) —
  gains three new `resolve_metric_names`/`resolve_options` branches (`geval_criteria`,
  `dag_builder`, `ragas_*.enabled`), same per-metric-name dispatch already used for
  `json_correctness`/`prompt_alignment`/`conversational_g_eval`.
- New: `deepeval_platform.llm.ragas_adapter.RagasLLMAdapter` — wraps a `DeepEvalBaseLLM` instance
  (obtained via the bot's already-resolved judge, same `LLMProviderFactory` path
  `EvaluationOrchestrator._resolve_judge()` already uses) to satisfy the subset of Ragas' LLM
  interface `AnswerCorrectness`/`ContextRecall` actually exercise (research.md §R3).
- `deepeval_platform.vector_store.qdrant_provider` (M1) — read-only reference; `RagasMetricWrapper`
  reuses its `OpenAIEmbeddings(model=..., api_key=...)` construction pattern but does not import
  from or modify `QdrantVectorStoreProvider` itself (FR-014).
- `deepeval_platform.evaluation.strategies.rag_strategy.RAGStrategy` (M2.1) — unchanged;
  `ragas_answer_correctness`/`ragas_context_recall` are opt-in only (FR-008), never added to
  `get_metrics()`.
- `deepeval_platform.evaluation.evaluation_orchestrator.EvaluationOrchestrator` (M3.1) —
  unchanged; all four new metrics run through its existing threshold/timeout/concurrency/isolation
  path (FR-011) with no signature or logic change (SC-005).
- `deepeval_platform.normalization.models.NormalizedTrace` (M2.2) — unchanged; `expected_output`
  and `context` are read for Ragas reference/retrieved-context inputs (per spec Clarifications).

**Storage**: N/A — no change to M3.1's in-memory-only scope.

**Testing**: `pytest`, `pytest-asyncio`, `pytest-mock`, `pytest-cov` with the project's existing
`--cov-fail-under=80` gate (Principle IV, NON-NEGOTIABLE TDD — tests precede implementation).
Ragas-specific tests mock the Ragas metric's `single_turn_ascore`/scoring call and
`RagasLLMAdapter`'s underlying `DeepEvalBaseLLM`, matching how M3.1-M3.3 tests mock the native
DeepEval `a_measure()` call — no real Ragas/LLM network calls in unit tests.

**Target Platform**: Linux server — same backend process as the rest of `deepeval_platform/`.

**Project Type**: Single project (existing `deepeval_platform/` package + `tests/`), no new
top-level project.

**Performance Goals**: No new target — all four wrappers run inside the same concurrent
`asyncio.gather()` + per-metric `asyncio.wait_for()` orchestration established in M3.1; nothing
here changes that mechanism (FR-011).

**Constraints**: Threshold/timeout configuration for all four new metrics follows the exact same
`ConfigManager`-based resolution and native-default fallback already generic in
`EvaluationOrchestrator` since M3.1 (Assumptions). `g_eval`, `dag`, and each Ragas metric
additionally require their own config key(s)/opt-in flag to be present or they are excluded
entirely (FR-003, FR-006, FR-008) — never attempted, never erroring for their absence. `dag`'s
activation additionally requires a versioned Python callable, not purely YAML (SC-006).

**Scale/Scope**: 3 new metric wrapper classes (`GEvalMetricWrapper`, `DAGMetricWrapper` — both
`MetricBase`; `RagasMetricWrapper` — one `MetricBase` subclass parameterized to back two canonical
names), 1 new adapter class (`RagasLLMAdapter`), 1 new dependency (`ragas>=0.2.0`), 3 new
`BotMetricConfigResolver` branches, 3 new optional `bots.yaml` key shapes (`geval_criteria`,
`dag_builder`, `bots.<bot>.metrics.ragas_{answer_correctness,context_recall}.enabled`).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Check | Status |
|---|---|---|
| I. OOP-First | Three single-responsibility wrapper classes (one parameterized, not duplicated, across two canonical names) plus one single-responsibility adapter class — matches the M3.1-M3.3 pattern; no monolithic additions | PASS |
| II. DeepEval-First | `GEvalMetricWrapper`/`DAGMetricWrapper` delegate 100% of scoring to native `GEval`/`DAGMetric` via `a_measure()`, verified against the installed package before writing this plan (research.md §R1/§R2). `RagasMetricWrapper` is the one deliberate exception, justified per the spec's Assumptions section rather than a blanket "no native equivalent" claim (that's only literally true for Answer Correctness — DeepEval already ships a native `ContextualRecallMetric`, integrated since M3.1): Ragas is added not to fill a coverage gap but explicitly for side-by-side comparison against DeepEval-native RAG metrics, "not to reimplement or supersede them" (spec.md Assumptions) — DeepEval remains this project's primary evaluation framework | PASS |
| III. LangChain-First | N/A for the evaluation-domain wrappers — out of scope per the principle's own text. `RagasLLMAdapter` explicitly avoids LangChain (`LangchainLLMWrapper`) in favor of adapting the project's existing `DeepEvalBaseLLM` judge directly (FR-009) — consistent with Principle III scoping LangChain to bot-orchestration code, not the evaluator's own judge-model wiring | PASS |
| IV. TDD (NON-NEGOTIABLE) | Tests written first for all three wrappers, `RagasLLMAdapter`, the three new `BotMetricConfigResolver` branches, and the `dag_builder` invoke-vs-use-as-is divergence; ≥80% coverage enforced by existing `pytest-cov` config | PASS (process gate, enforced during `/speckit-tasks` + `/speckit-implement`) |
| V. Zero Hardcode | No new credentials. `ragas` judge/embeddings config reuses existing `ConfigManager`-governed keys (`evaluation.llm_judge.*` via the existing judge resolution path, `embedding.model`/`embedding.dimensions`) — no new secret, no new config file, `BotMetricConfigResolver` remains the sole `bots.yaml`-key reader for these three metrics (reads exclusively through `ConfigManager`) | PASS |
| VI. Design Patterns | All three wrappers self-register via the existing `MetricFactory.create(name)` Factory Method — `RagasMetricWrapper` registers twice (once per canonical name) with zero if/else branches added to the factory itself; `RagasLLMAdapter` is a plain single-responsibility adapter, not a new pattern requiring a Design Patterns table entry | PASS |

No violations — Complexity Tracking table is not needed.

## Project Structure

### Documentation (this feature)

```text
specs/007-custom-metrics/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md        # Phase 1 output (/speckit-plan command)
├── quickstart.md        # Phase 1 output (/speckit-plan command)
├── contracts/
│   └── evaluation-api.md   # Phase 1 output — additions to the 004/006 contract (BotMetricConfigResolver new branches, RagasLLMAdapter surface, new bots.yaml keys)
└── tasks.md             # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
deepeval_platform/
├── evaluation/
│   ├── bot_metric_config_resolver.py            # MODIFIED — three new opt-in branches (geval_criteria, dag_builder [invoked], ragas_*.enabled)
│   └── metrics/
│       └── native/
│           ├── __init__.py                       # MODIFIED — imports the three new wrapper modules
│           ├── g_eval_metric.py                   # NEW — GEvalMetricWrapper (registers "g_eval")
│           ├── dag_metric.py                      # NEW — DAGMetricWrapper (registers "dag")
│           └── ragas_metric.py                    # NEW — RagasMetricWrapper (registers "ragas_answer_correctness" and "ragas_context_recall")
└── llm/
    └── ragas_adapter.py                          # NEW — RagasLLMAdapter (DeepEvalBaseLLM -> Ragas LLM interface)

config/
└── bots.yaml                                    # MODIFIED — optional new keys per data-model.md (geval_criteria, dag_builder, metrics.ragas_answer_correctness.enabled, metrics.ragas_context_recall.enabled)

pyproject.toml                                    # MODIFIED — adds "ragas>=0.2.0"

tests/
└── unit/
    ├── evaluation/
    │   ├── test_bot_metric_config_resolver.py     # MODIFIED — new cases for geval_criteria/dag_builder/ragas opt-in resolution
    │   └── metrics/
    │       └── native/
    │           ├── test_g_eval_metric.py           # NEW
    │           ├── test_dag_metric.py               # NEW
    │           └── test_ragas_metric.py              # NEW
    └── llm/
        └── test_ragas_adapter.py                  # NEW
```

**Structure Decision**: Single project, extending the existing `deepeval_platform/evaluation/`
domain package in place — three new wrapper modules land in the same `metrics/native/` sub-package
M3.1-M3.3 already established, alongside one new module in the existing `llm/` package
(`ragas_adapter.py`, sibling to `base.py`/`factory.py`) since it adapts an LLM provider concern, not
an evaluation-metric concern. No new top-level project, no new sub-package.

## Complexity Tracking

*No violations — table intentionally left empty.*

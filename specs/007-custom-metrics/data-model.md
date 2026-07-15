# Phase 1 Data Model: Custom Metrics Integration (GEval, DAG, Ragas) (M3.4)

No changes to `NormalizedTrace`, `EvaluationContext`, `EvaluationResult`, `MetricResult`,
`MetricFactory.register()`/`MetricFactory.create()`, or `EvaluationOrchestrator`'s public signature
(SC-005). This document covers only the new classes and the resolver/config additions.

## GEvalMetricWrapper (new — `deepeval_platform/evaluation/metrics/native/g_eval_metric.py`)

`MetricBase` subclass (research.md §R1). Does not override `_build_test_case` — operates on the
same `LLMTestCase` fields every M3.1-M3.3 single-turn wrapper already populates.

| Member | Type | Notes |
|---|---|---|
| `_native_metric_cls` | `ClassVar[type[BaseMetric]]` | `GEval` |
| `__init__(threshold, deepeval_model, criteria)` | — | `self._native = GEval(name="Custom Criteria", criteria=criteria, evaluation_params=[SingleTurnParams.INPUT, SingleTurnParams.ACTUAL_OUTPUT], threshold=threshold, model=deepeval_model, async_mode=True)` — `evaluation_params` is fixed, not bot-configurable (research.md §R1); `name` is a fixed literal, matching `ConversationalGEvalMetricWrapper`'s precedent (M3.3) |
| canonical name | — | `g_eval` |

## DAGMetricWrapper (new — `deepeval_platform/evaluation/metrics/native/dag_metric.py`)

`MetricBase` subclass (research.md §R2). Does not override `_build_test_case`.

| Member | Type | Notes |
|---|---|---|
| `_native_metric_cls` | `ClassVar[type[BaseMetric]]` | `DAGMetric` |
| `__init__(threshold, deepeval_model, dag)` | — | `self._native = DAGMetric(name="Decision Graph", dag=dag, threshold=threshold, model=deepeval_model, async_mode=True)` — `dag` is a live `DeepAcyclicGraph` instance, already constructed by the time it reaches this wrapper (resolution/invocation happens in `BotMetricConfigResolver`, not here) |
| canonical name | — | `dag` |

## RagasMetricWrapper (new — `deepeval_platform/evaluation/metrics/native/ragas_metric.py`)

`MetricBase` subclass that does **not** delegate to a native DeepEval class for scoring
(research.md §R3/§R4) — overrides both `__init__` and `measure()`. `RagasMetricWrapper` itself is
**not** registered with `@MetricFactory.register(...)`; it holds the shared construction/measure
logic, parameterized by `ragas_metric_name`. Two thin subclasses — `_AnswerCorrectnessMetricWrapper`
and `_ContextRecallMetricWrapper`, each hardcoding its `ragas_metric_name` via `super().__init__()`
— are the ones actually decorated with `@MetricFactory.register(...)`, one name each, so the
factory's `_registry` holds two distinct classes rather than one class shared via
`functools.partial` (see the `_native_metric_cls` row below for why that distinction matters). The
module's `ragas.*` imports are guarded (`try`/`except ImportError`, research.md §R5): both
subclasses' bodies and `@MetricFactory.register(...)` decorators evaluate without referencing the
guarded names, so both canonical names register successfully even when `ragas` is not installed —
the resulting `ImportError` is deferred to `__init__` (see that row below), keeping the failure
isolated to whichever Ragas metric a bot actually opts into (FR-010).

| Member | Type | Notes |
|---|---|---|
| `_native_metric_cls` | `ClassVar[type]` | Points at a local `_RagasThresholdDefault` placeholder class (`__init__(self, threshold: float = 0.5)`) rather than a real native DeepEval class. Exists solely so `EvaluationOrchestrator._native_default_threshold`'s unmodified `_registry[name]._native_metric_cls` + `inspect.signature(...).parameters["threshold"].default` lookup keeps resolving a numeric default (`0.5`) for a bot that enables a Ragas metric without configuring its own threshold — without this, `_registry[name]` would need to be something other than an ordinary class (e.g. a bare `functools.partial`), which has no `_native_metric_cls` attribute and would make `_native_default_threshold` raise `AttributeError`, aborting the whole `evaluate()` call (FR-011/SC-004). Both subclasses inherit this ClassVar unchanged. Note: `MetricBase` declares this as `ClassVar[type[BaseMetric]]`; `_RagasThresholdDefault` does not subclass DeepEval's `BaseMetric`, so `RagasMetricWrapper` intentionally narrows the annotation to the looser `ClassVar[type]` shown above for this one subclass — harmless at runtime (no mypy/type-checker gate exists in this repo today) and consistent with `RagasMetricWrapper` being the one deliberate `MetricBase` exception (research.md §R4). |
| `__init__(threshold, deepeval_model, ragas_metric_name)` | — | First checks the module-level `_RAGAS_IMPORT_ERROR` guard (research.md §R5) and raises `ImportError` immediately if `ragas` isn't installed — **before** referencing `AnswerCorrectness`/`ContextRecall`/`SingleTurnSample`, so a missing install fails only this constructor call, not module import. Otherwise: `ragas_metric_name: Literal["answer_correctness", "context_recall"]`, supplied by each subclass's own `__init__`, never by the caller directly. Builds the judge via `RagasLLMAdapter(deepeval_model)`; for `"answer_correctness"` only, also builds an `OpenAIEmbeddings(model=..., api_key=...)` (same construction `QdrantVectorStoreProvider` uses, FR-014) wrapped in Ragas' own `ragas.embeddings.LangchainEmbeddingsWrapper`. Constructs `AnswerCorrectness(llm=adapter, embeddings=wrapped_embeddings)` or `ContextRecall(llm=adapter)` accordingly and stores it as `self._ragas_metric`. Stores `threshold` on `self._threshold` and initializes `self._passed: bool \| None = None` (no native `.threshold`/`.success` to proxy — research.md §R4) |
| `threshold` | `property -> float` | `self._threshold` |
| `passed` | `property -> bool \| None` | `self._passed` |
| `measure(context) -> MetricResult` | `async`, **overridden** | Builds a `SingleTurnSample` from `context.trace` per the field-mapping table below, `await self._ragas_metric.single_turn_ascore(sample)`, sets `self._passed = score >= self._threshold`, returns `MetricResult(score=score, threshold=self._threshold, passed=self._passed, error=None)` |
| canonical names | — | `ragas_answer_correctness` (`_AnswerCorrectnessMetricWrapper`, calls `super().__init__(..., ragas_metric_name="answer_correctness")`), `ragas_context_recall` (`_ContextRecallMetricWrapper`, calls `super().__init__(..., ragas_metric_name="context_recall")`) — two ordinary registered subclasses, each its own `@MetricFactory.register(...)` application; `MetricFactory.create()`'s call shape (`threshold=`, `deepeval_model=`, `**options`) is unaffected |

`SingleTurnSample` field mapping (research.md §R3; both metrics read `user_input`/`reference`,
each also reads its one metric-specific field):

| `SingleTurnSample` field | Source | `answer_correctness` | `context_recall` |
|---|---|:---:|:---:|
| `user_input` | `trace.input` | ✅ | ✅ |
| `response` | `trace.output` | ✅ | — |
| `reference` | `trace.expected_output` | ✅ | ✅ |
| `retrieved_contexts` | `trace.context` (coerced to `list[str]`) | — | ✅ |

## RagasLLMAdapter (new — `deepeval_platform/llm/ragas_adapter.py`)

Implements the subset of `ragas.llms.base.BaseRagasLLM` that `AnswerCorrectness`/`ContextRecall`
exercise (research.md §R3), adapting a `DeepEvalBaseLLM` instance — never a LangChain chat model
(Principle III; FR-009).

| Member | Type | Notes |
|---|---|---|
| `__init__(deepeval_model: DeepEvalBaseLLM)` | — | stores the wrapped judge model |
| `agenerate_text(prompt, n=1, temperature=0.01, stop=None, callbacks=None) -> LLMResult` | `async`, required override | calls `await self._deepeval_model.a_generate(prompt.to_string())`, wraps the returned string into Ragas' `LLMResult`/`Generation` shape |
| `generate_text(...)` | required override (sync ABC method) | thin sync wrapper (`asyncio.run`/existing event-loop pattern), present only to satisfy `BaseRagasLLM`'s abstract contract — not on `RagasMetricWrapper.measure()`'s call path, which is exclusively async |
| `is_finished(response) -> bool` | required override | returns `True` — DeepEval's provider abstraction has no partial/streaming-completion concept to check (research.md §R3) |

Does **not** modify `LLMProviderFactory` or any concrete provider class (FR-009).

## BotMetricConfigResolver (modified — `deepeval_platform/evaluation/bot_metric_config_resolver.py`)

Four new opt-in checks (two share a `resolve_options` fall-through), following the exact
per-metric-name dispatch M3.3 already established: `resolve_metric_names` gains 2 new independent
truthy checks (`g_eval`, `dag`) plus 2 more for the Ragas names (tasks.md T018), for 4 total; only 2
new `resolve_options` branches are needed since both Ragas names fall through to the existing
generic `{}` case. No new method signatures; `resolve_metric_names`/`resolve_options` keep their
existing shapes.

| Metric | `resolve_metric_names` inclusion check | `resolve_options` resolution |
|---|---|---|
| `g_eval` | `bots.<bot>.geval_criteria` present (truthy string) | `{"criteria": <string>}` |
| `dag` | `bots.<bot>.dag_builder` present (truthy string) | dotted path → `importlib.import_module` + `getattr` → **invoked with zero args** → `{"dag": <DeepAcyclicGraph instance>}` (research.md §R2 — the one divergence from `json_schema`'s as-is resolution) |
| `ragas_answer_correctness` | `bots.<bot>.metrics.ragas_answer_correctness.enabled` truthy (research.md §R6) | `{}` — no bot-specific constructor kwarg; `ragas_metric_name` is fixed per canonical name at the `MetricFactory` registration level, not resolved per-bot |
| `ragas_context_recall` | `bots.<bot>.metrics.ragas_context_recall.enabled` truthy (research.md §R6) | `{}` |

Append order in `resolve_metric_names` (extends M3.3's fixed order): `summarization`,
`json_correctness`, `prompt_alignment`, `conversational_g_eval`, `g_eval`, `dag`,
`ragas_answer_correctness`, `ragas_context_recall`. All four new checks are independent — any
subset may be present for a given bot (spec Edge Cases).

## Modified: `RAGStrategy` — no change

`get_metrics()` is unchanged. `ragas_answer_correctness`/`ragas_context_recall` are opt-in only
(FR-008) — reaching them always goes through `BotMetricConfigResolver`, never through
`RAGStrategy.get_metrics()`. Same for `g_eval`/`dag` and every `EvaluationStrategy` (FR-003/FR-006
— none is added to any strategy's automatic list).

## Modified: bot configuration schema (`config/bots.yaml`)

New optional per-bot keys (all read exclusively through `ConfigManager`, Principle V):

| Key | Type | Unlocks |
|---|---|---|
| `bots.<bot>.geval_criteria` | string | `g_eval` opt-in (FR-002) |
| `bots.<bot>.dag_builder` | string (dotted import path to a zero-arg callable) | `dag` opt-in (FR-005) |
| `bots.<bot>.metrics.ragas_answer_correctness.enabled` | bool | `ragas_answer_correctness` opt-in (FR-008) |
| `bots.<bot>.metrics.ragas_context_recall.enabled` | bool | `ragas_context_recall` opt-in (FR-008) |

## Modified: `pyproject.toml`

Adds `ragas>=0.2.0` to `[project].dependencies` (FR-010).

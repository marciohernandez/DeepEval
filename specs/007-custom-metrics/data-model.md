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

`MetricBase` subclass that does **not** delegate to a native DeepEval class (research.md §R3/§R4)
— no `_native_metric_cls`, overrides both `__init__` and `measure()`. One class backs both
canonical names via a constructor-time selector; `MetricFactory.register()` is called twice on the
same class (once per name), so the factory itself needs no branching.

| Member | Type | Notes |
|---|---|---|
| `__init__(threshold, deepeval_model, ragas_metric_name)` | — | `ragas_metric_name: Literal["answer_correctness", "context_recall"]`. Builds the judge via `RagasLLMAdapter(deepeval_model)`; for `"answer_correctness"` only, also builds an `OpenAIEmbeddings(model=..., api_key=...)` (same construction `QdrantVectorStoreProvider` uses, FR-014) wrapped in Ragas' own `ragas.embeddings.LangchainEmbeddingsWrapper`. Constructs `AnswerCorrectness(llm=adapter, embeddings=wrapped_embeddings)` or `ContextRecall(llm=adapter)` accordingly and stores it as `self._ragas_metric`. Stores `threshold` on `self._threshold` and initializes `self._passed: bool \| None = None` (no native `.threshold`/`.success` to proxy — research.md §R4) |
| `threshold` | `property -> float` | `self._threshold` |
| `passed` | `property -> bool \| None` | `self._passed` |
| `measure(context) -> MetricResult` | `async`, **overridden** | Builds a `SingleTurnSample` from `context.trace` per the field-mapping table below, `await self._ragas_metric.single_turn_ascore(sample)`, sets `self._passed = score >= self._threshold`, returns `MetricResult(score=score, threshold=self._threshold, passed=self._passed, error=None)` |
| canonical names | — | `ragas_answer_correctness` (registered with `ragas_metric_name="answer_correctness"`), `ragas_context_recall` (registered with `ragas_metric_name="context_recall"`) — two `@MetricFactory.register(...)` applications, same class, distinguished by a small factory wrapper/partial per name (implementation detail for tasks.md; `MetricFactory.create()`'s call shape — `threshold=`, `deepeval_model=`, `**options` — is unaffected either way) |

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

Three new branches, following the exact per-metric-name dispatch M3.3 already established. No new
method signatures; `resolve_metric_names`/`resolve_options` keep their existing shapes.

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

# Phase 0 Research: Custom Metrics Integration (GEval, DAG, Ragas) (M3.4)

## R1. `GEval` — `evaluation_params` is required at measure time, unlike every prior single-criterion wrapper

Verified against installed `deepeval==4.0.7` (`deepeval/metrics/g_eval/g_eval.py`):

```python
GEval.__init__(
    name: str,
    evaluation_params: list[SingleTurnParams] | None = None,
    criteria: str | None = None,
    evaluation_steps: list[str] | None = None,
    rubric: list[Rubric] | None = None,
    model=None, threshold: float = 0.5, ..., async_mode: bool = True,
)
```

`evaluation_params=None` is accepted silently at construction (only `len(evaluation_params) == 0`
raises there). But `measure()`/`a_measure()` both call `ensure_required_params(self.evaluation_params,
self.criteria, self.evaluation_steps)` first, which raises `ValueError("GEval requires
evaluation_params. Provide them at initialization or call pull() before evaluate.")` whenever
`evaluation_params` is falsy. `ConversationalGEval` (M3.3) does not hit this because
`ConversationalMetricBase`'s native class does not require it the same way for the
`ConversationalTestCase` case.

**Decision**: `GEvalMetricWrapper.__init__` passes `evaluation_params=[SingleTurnParams.INPUT,
SingleTurnParams.ACTUAL_OUTPUT]` explicitly, alongside the bot-configured `criteria` — the minimal
pair every GEval usage needs (matches DeepEval's own quick-start example) and the two fields every
`NormalizedTrace` already carries, so no bot-configured evaluation_params list is needed for this
milestone (consistent with the spec's Assumptions: only free-text `criteria` is in scope, not
`evaluation_steps`/`rubric`).

**Alternatives considered**: Making `evaluation_params` itself a bot-configurable list (rejected —
not in FR-002's scope, adds a second config key for no requested use case this milestone).

## R2. `DAGMetric` construction has no equivalent required-param trap; `dag_builder` diverges from `json_schema`'s pattern by needing invocation

Verified against installed `deepeval==4.0.7`:

```python
DAGMetric.__init__(
    name: str,
    dag: DeepAcyclicGraph,
    model=None, threshold: float = 0.5, include_reason: bool = True,
    async_mode: bool = True, ...,
)
```

No other required construction-time value beyond `dag` — same generic shape every other
`MetricBase` subclass's extra kwarg already follows. `deepeval.metrics.dag` also exports
`dag_from_dict`/`dag_from_json` (a declarative graph-from-data path), confirming a generic
YAML/JSON graph parser is technically available upstream — but the spec's clarification explicitly
rejects that path in favor of a versioned Python callable (FR-005, edge cases), so this feature
does not use `dag_from_dict`/`dag_from_json`.

The one real divergence: `BotMetricConfigResolver._resolve_json_correctness_options` (M3.3)
resolves `bots.<bot>.json_schema` via `importlib.import_module` + `getattr` and uses the resolved
attribute **as-is** (a class, never called). FR-005's own clarification requires `dag_builder`'s
resolved attribute to instead be **invoked with zero arguments** to produce the
`DeepAcyclicGraph` — so `_resolve_dag_options` reuses the same two-line import/getattr mechanic but
adds one call: `getattr(module, class_name)()`.

**Decision**: `_resolve_dag_options(bot_id)` mirrors `_resolve_json_correctness_options` exactly
except for that trailing `()`. No new resolution helper, no caching (Assumptions: resolved once per
metric construction, matching `json_schema`'s existing behavior).

## R3. Ragas `0.2.x` API surface for `AnswerCorrectness` / `ContextRecall`

Not yet installed in this environment (`ModuleNotFoundError: No module named 'ragas'` — confirmed).
Verified against Ragas' own source (`explodinggradients/ragas`, `v0.2.3` docs) and current `main`:

- **`SingleTurnSample`** (`ragas.dataset_schema`) — the per-row input shape. Fields relevant here:
  `user_input: str`, `response: str | None`, `reference: str | None`,
  `retrieved_contexts: list[str] | None`.
- **`AnswerCorrectness`** (`ragas.metrics`, instance exported as `answer_correctness`) — inherits
  `MetricWithLLM` + `MetricWithEmbeddings`. `_required_columns[SINGLE_TURN] = {"user_input",
  "response", "reference"}`. Combines an LLM-judged factual-correctness (F-beta over
  TP/FP/FN-classified statements) and embeddings-based semantic-similarity score, weighted
  `[0.75, 0.25]` by default (`weights` param) — matches the spec's Clarifications description of
  "a factual-correctness score combined with a semantic-similarity score."
- **`ContextRecall`** (`ragas.metrics`, instance exported as `context_recall` /
  `LLMContextRecall`) — inherits `MetricWithLLM` only (no embeddings needed).
  `_required_columns[SINGLE_TURN] = {"user_input", "retrieved_contexts", "reference"}`.
- Both expose `async single_turn_ascore(sample: SingleTurnSample, callbacks=None) -> float` as the
  stable scoring entry point (the synchronous/legacy `score()` path is deprecated toward 0.3).

**`NormalizedTrace` → `SingleTurnSample` field mapping** (per spec Clarifications — reuses
`expected_output`/`context`, no new fields added anywhere):

| `SingleTurnSample` field | Source | Used by |
|---|---|---|
| `user_input` | `trace.input` | both |
| `response` | `trace.output` | `AnswerCorrectness` only |
| `reference` | `trace.expected_output` | both |
| `retrieved_contexts` | `trace.context` (coerced to `list[str]`) | `ContextRecall` only |

**LLM interface — `BaseRagasLLM`** (`ragas.llms.base`): abstract methods a subclass must implement:
`generate_text(prompt: PromptValue, n=1, temperature=0.01, stop=None, callbacks=None) -> LLMResult`,
an async `agenerate_text(...)` counterpart, and `is_finished(response: LLMResult) -> bool`. This is
the interface `RagasLLMAdapter` (FR-009) implements — no LangChain (`LangchainLLMWrapper`) is used
for this role, since the project's judge model is a `DeepEvalBaseLLM`, not a LangChain chat model
(Principle III scopes LangChain to bot orchestration only). `RagasLLMAdapter` needs only the async
path (`agenerate_text`), since `MetricBase.measure()` is already async end-to-end — `generate_text`
and `is_finished` still need trivial implementations to satisfy the ABC, per the spec's Assumptions
("only the subset ... actually exercised by Answer Correctness and Context Recall").

**Embeddings interface — `BaseRagasEmbeddings`** (`ragas.embeddings.base`): Ragas ships its own
`LangchainEmbeddingsWrapper` that adapts any LangChain `Embeddings` instance (sync/async
`embed_query`/`embed_documents`) into `BaseRagasEmbeddings` directly — no custom adapter class
needed on this side. This is the same `OpenAIEmbeddings` object `QdrantVectorStoreProvider` already
constructs (`langchain_openai.OpenAIEmbeddings(model=..., api_key=...)`), so
`RagasMetricWrapper`/its construction path builds one more `OpenAIEmbeddings` instance the same way
and wraps it with Ragas' own `LangchainEmbeddingsWrapper` — FR-014 is explicit this must not
introduce a new embeddings provider or touch `QdrantVectorStoreProvider`, and using Ragas' own
official LangChain-embeddings adapter satisfies that without hand-rolling one.

**Decision**: `RagasMetricWrapper` overrides `measure()` (not `_build_test_case`, since it never
builds an `LLMTestCase`) — build a `SingleTurnSample` from the table above, call
`await ragas_metric_instance.single_turn_ascore(sample)`, map the returned `float` into
`MetricResult(score=..., threshold=..., passed=score >= threshold, error=None)`. `answer_correctness`
also needs the embeddings instance passed to its constructor (`AnswerCorrectness(llm=...,
embeddings=...)`); `context_recall` needs only `llm=...` — the wrapper accepts a
`ragas_metric` selector so one class backs both canonical names without branching in
`MetricFactory`.

**Alternatives considered**: `ragas.evaluate()` (the batch/dataset-oriented top-level API) —
rejected, it's designed around `EvaluationDataset`/pandas batch scoring, not the
single-trace-at-a-time, per-metric-isolated `measure()` contract every other wrapper in this
project implements; `single_turn_ascore()` is the documented single-sample entry point and is what
every other wrapper's `a_measure()` equivalent already looks like structurally.

## R4. `RagasMetricWrapper` cannot extend `MetricBase`'s default `measure()` — it overrides directly

`MetricBase.measure()` (M3.1) is generic across every prior wrapper because they all delegate to a
native DeepEval `BaseMetric` with a uniform `a_measure(test_case)` shape. Ragas has no DeepEval
`BaseMetric` to wrap and a structurally different sample type (`SingleTurnSample`, not
`LLMTestCase`). `RagasMetricWrapper` therefore subclasses `MetricBase` (for `threshold`/API-contract
uniformity and so `MetricFactory.create()`'s call shape — `threshold=`, `deepeval_model=`, `**options`
— stays identical for every registered name, FR-011/SC-005) but overrides both `__init__` (no
`self._native_metric_cls` — it builds a Ragas metric instance instead, not a DeepEval one) and
`measure()` (talks to Ragas' `single_turn_ascore`, not `a_measure`). `threshold`/`passed` become
plain attributes set on `self` rather than proxied through a native DeepEval object's `.threshold`/
`.success`, since there is no such object here.

**Decision confirmed against Principle I (OOP-First)**: this is still a legitimate `MetricBase`
subclass — polymorphism from `EvaluationOrchestrator`'s point of view is preserved (same
`threshold`/`passed`/`async measure(context) -> MetricResult` surface); only the *internal*
delegation target changes, which is exactly what subclassing an ABC is for.

## R5. Ragas package absence is isolated via a guarded import inside `ragas_metric.py` — module-load time must never raise

Edge case (spec): "a Ragas metric when the `ragas` package is not installed... is treated as an
isolated failure of that metric only." A naive top-level `from ragas.metrics import
AnswerCorrectness, ContextRecall` / `from ragas.dataset_schema import SingleTurnSample` inside
`ragas_metric.py` would raise `ImportError` the moment
`deepeval_platform.evaluation.metrics.native.__init__` imports that module at package-load
time — which breaks *every* metric's registration (`g_eval`, `dag`, and every M3.1-M3.3 native
wrapper), not just the two Ragas names, violating FR-010/SC-003. This is a real gap, not a
hypothetical: it fires on any environment where `uv sync` hasn't (yet, or successfully) installed
`ragas` — which the Edge Case explicitly names as the scenario to isolate, not exclude.

**Decision**: `ragas` remains a normal (non-optional) direct dependency (`ragas>=0.2.0`, FR-010),
installed via `uv sync` like every other dependency — but `ragas_metric.py` guards its own
`ragas.*` imports at the top of the module:

```python
try:
    from ragas.dataset_schema import SingleTurnSample
    from ragas.embeddings import LangchainEmbeddingsWrapper
    from ragas.metrics import AnswerCorrectness, ContextRecall
    _RAGAS_IMPORT_ERROR: Exception | None = None
except ImportError as exc:  # pragma: no cover - exercised via monkeypatched flag in tests
    _RAGAS_IMPORT_ERROR = exc
```

`RagasMetricWrapper.__init__` checks `_RAGAS_IMPORT_ERROR` first and, if set, raises immediately
(`raise ImportError("ragas is not installed; run `uv sync`") from _RAGAS_IMPORT_ERROR`) — before
touching `AnswerCorrectness`/`ContextRecall`/`SingleTurnSample` at all. Both
`_AnswerCorrectnessMetricWrapper`/`_ContextRecallMetricWrapper` **class definitions** (and their
`@MetricFactory.register(...)` decorators) do not reference the guarded names at class-body
evaluation time, so they still define and register successfully even when `ragas` is absent —
`deepeval_platform.evaluation.metrics.native.__init__`'s import of `ragas_metric` always succeeds,
and both canonical names remain present in `MetricFactory._registry`. This matters beyond just
avoiding the module-load crash: `EvaluationOrchestrator.evaluate()` pre-flight-checks every
requested metric name against `MetricFactory._registry` *before* `_measure_one`'s per-metric
try/except runs (`evaluation_orchestrator.py:50`) — if either Ragas name were simply left
unregistered when `ragas` is missing, a bot that opts into it would hit `UnknownMetricError` for
the *entire* `evaluate()` call, aborting sibling metrics too, which is the same class of violation
via a different code path. Keeping both names always-registered, and deferring the failure to
construction time inside `_measure_one`'s existing try/except (M3.1), is what actually isolates
the failure to the one opted-in Ragas metric per FR-010/the Edge Case.

Misconfiguration once `ragas` **is** installed (bad credentials, embedding config) is still an
ordinary exception surfacing from inside `measure()`/`__init__` construction, isolated by
`EvaluationOrchestrator._measure_one`'s existing generic `except Exception` catch (M3.1) —
consistent with how every other opt-in metric's misconfiguration is already isolated. No
orchestrator change is needed for that part; the guard above only closes the module-load-time gap.

## R6. `bots.<bot>.metrics.ragas_answer_correctness.enabled` / `...ragas_context_recall.enabled` — same truthy pattern as `summarization`

`BotMetricConfigResolver.resolve_metric_names` (M3.3) already has the exact shape needed —
`config.get_optional(f"bots.{bot_id}.metrics.summarization.enabled", default="")` checked against
`_TRUTHY_VALUES`. FR-008 asks for the identical pattern per Ragas metric name.

**Decision**: two more `if` blocks in `resolve_metric_names`, same truthy-check helper, appending
`"ragas_answer_correctness"` / `"ragas_context_recall"` independently (a bot may enable one without
the other — spec Edge Cases: all four new metrics, including both Ragas ones, are independent and
non-blocking of each other).

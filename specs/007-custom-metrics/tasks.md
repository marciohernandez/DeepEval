# Tasks: Custom Metrics Integration (GEval, DAG, Ragas) (M3.4)

**Input**: Design documents from `/specs/007-custom-metrics/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/evaluation-api.md, quickstart.md

**Tests**: Included and REQUIRED — constitution Principle IV (TDD, NON-NEGOTIABLE) and plan.md's
Testing section mandate tests before implementation for every module in this milestone, enforced
by the existing `pytest-cov --cov-fail-under=80` gate.

**Organization**: Tasks are grouped by user story (spec.md priorities P1/P2/P3) to enable
independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3)
- File paths are exact and relative to the repository root

## Path Conventions

Single project (existing `deepeval_platform/` package + `tests/`), per plan.md's Project
Structure — no new top-level project, no new sub-package. All three new wrapper modules land in
the `deepeval_platform/evaluation/metrics/native/` sub-package M3.1-M3.3 already established;
`RagasLLMAdapter` lands in the existing `deepeval_platform/llm/` package, sibling to `base.py`/
`factory.py`.

## A design gap closed during task generation

`EvaluationOrchestrator._native_default_threshold(name)` (unchanged per SC-005) does
`MetricFactory._registry[name]._native_metric_cls` then
`inspect.signature(native_cls.__init__).parameters["threshold"].default` whenever a bot does not
configure `bots.<bot>.metrics.<name>.threshold` explicitly. `RagasMetricWrapper` has no wrapped
native DeepEval class (data-model.md), so registering it via a bare `functools.partial` (the
contract's own phrasing, "e.g. via a small `functools.partial`-style binding") would make
`_registry[name]` a `functools.partial` object with no `_native_metric_cls` attribute at all —
`_native_default_threshold` would raise `AttributeError` for any Ragas metric left at its default
threshold, which is not a per-metric-isolated failure (it happens inside `_resolve_thresholds`,
before `_measure_one`'s try/except, aborting the *entire* `evaluate()` call via
`ConfigResolutionError`) — violating FR-011/SC-004 without any spec/plan/research/data-model text
flagging it. T017 below resolves this the way the contract's closing sentence actually points
("these are simply two more ordinary registered **subclasses**"): two thin `RagasMetricWrapper`
subclasses, each registered directly (not via `functools.partial`), inheriting a `_native_metric_cls`
ClassVar that points at a tiny local placeholder class exposing `threshold: float = 0.5` purely so
`inspect.signature(...).parameters["threshold"].default` keeps resolving to `0.5` — the same
default every other native metric in this project uses — with zero change to
`EvaluationOrchestrator` (SC-005 preserved) and zero new orchestrator-side special-casing.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Add the one new project dependency this milestone introduces.

- [X] T001 Add `"ragas>=0.2.0"` to the `dependencies` list in `pyproject.toml` (FR-010), then run
  `uv sync` to install it — required before T013/T014/T017/T019 can import from `ragas.*`. Also
  pinned `"langchain-community>=0.4.0,<0.4.2"` as a direct dependency: `ragas` (0.2.x-0.4.x, all
  tested) unconditionally imports `langchain_community.chat_models.vertexai` at module load, which
  langchain-community removed in 0.4.2+; nothing else in this project imports `langchain_community`,
  and `langchain`/`langchain-core` remain on the required v1.x line.

---

## Phase 2: Foundational (Blocking Prerequisites)

**N/A** — `MetricBase`, `MetricFactory`, and `BotMetricConfigResolver` (M3.1/M3.3) already provide
every extension point this milestone needs; each user story below adds its own wrapper module and
its own resolver branch with no shared new abstraction required first (unlike M3.3's Phase 2,
which had to introduce `ConversationalMetricBase` and generalize `MetricFactory.create()` before
any story could proceed).

---

## Phase 3: User Story 1 - Avaliar critérios de qualidade customizados por bot com GEval (Priority: P1) 🎯 MVP

**Goal**: Register `GEvalMetricWrapper` under the canonical name `g_eval`, available only when a
bot's `bots.yaml` entry declares `geval_criteria` — no `EvaluationStrategy.get_metrics()` change.

**Independent Test**: Configure a sample bot with `geval_criteria` in `config/bots.yaml`, build an
`EvaluationContext` from a `NormalizedTrace` for that bot, run evaluation with `g_eval` in
`metric_names`, and confirm `EvaluationResult` contains a `g_eval` entry with score/threshold/status.

### Tests for User Story 1 ⚠️

> Write these tests FIRST, ensure they FAIL before implementation.

- [X] T002 [P] [US1] Write `tests/unit/evaluation/metrics/native/test_g_eval_metric.py`:
  `test_registered_under_canonical_name` (`MetricFactory._registry["g_eval"] is GEvalMetricWrapper`),
  `test_wraps_native_g_eval` (`GEvalMetricWrapper._native_metric_cls is GEval` from
  `deepeval.metrics`), and `test_criteria_and_fixed_evaluation_params_forwarded_to_native_constructor`
  (`GEvalMetricWrapper(threshold=0.5, deepeval_model=MagicMock(spec=DeepEvalBaseLLM),
  criteria="Response must stay formal and never promise a delivery date")` constructs its native
  `GEval` with that exact `criteria`, a fixed literal `name` (data-model.md: not bot-configurable
  this milestone, matching `ConversationalGEvalMetricWrapper`'s precedent), and
  `evaluation_params == [SingleTurnParams.INPUT, SingleTurnParams.ACTUAL_OUTPUT]` — asserting the
  research.md §R1 fix (native `GEval.measure()` raises `ValueError` when `evaluation_params` is
  falsy; this wrapper must never hit that path)
- [X] T003 [P] [US1] Update `tests/unit/evaluation/test_bot_metric_config_resolver.py`: add
  `test_g_eval_appended_only_when_geval_criteria_set` and
  `test_g_eval_omitted_when_geval_criteria_absent` to `TestResolveMetricNames`, and
  `test_g_eval_resolves_criteria` (`resolve_options("test_bot", ["g_eval"])` with
  `bots.test_bot.geval_criteria` stubbed returns `{"g_eval": {"criteria": "<the stubbed value>"}}`)
  to `TestResolveOptions` — mirrors the existing `conversational_g_eval` cases exactly

### Implementation for User Story 1

- [X] T004 [US1] Implement `deepeval_platform/evaluation/metrics/native/g_eval_metric.py`:
  `GEvalMetricWrapper(MetricBase)` with `_native_metric_cls = GEval` (`from deepeval.metrics import
  GEval`), `__init__(self, threshold: float, deepeval_model: DeepEvalBaseLLM, criteria: str)`
  constructing `self._native = GEval(name="Custom Criteria", criteria=criteria,
  evaluation_params=[SingleTurnParams.INPUT, SingleTurnParams.ACTUAL_OUTPUT], threshold=threshold,
  model=deepeval_model, async_mode=True)` (`SingleTurnParams` from `deepeval.test_case`, verified
  importable against installed `deepeval==4.0.7`), `@MetricFactory.register("g_eval")` — no
  `_build_test_case` override, same as every other single-turn wrapper — makes T002 pass
- [X] T005 [US1] Update `deepeval_platform/evaluation/bot_metric_config_resolver.py`: in
  `resolve_metric_names`, append a check `if self._config.get_optional(f"bots.{bot_id}.geval_criteria",
  default=""):  metric_names.append("g_eval")` immediately after the existing
  `conversational_g_eval` check (data-model.md's fixed append order); in `resolve_options`, add
  `elif name == "g_eval": options[name] = self._resolve_g_eval_options(bot_id)` and a
  `_resolve_g_eval_options(self, bot_id)` method returning
  `{"criteria": self._config.get_optional(f"bots.{bot_id}.geval_criteria", default="")}` — makes
  T003 pass
- [X] T006 [US1] Update `deepeval_platform/evaluation/metrics/native/__init__.py`: add
  `g_eval_metric,  # noqa: F401` to the existing alphabetically-ordered import tuple, immediately
  before `hallucination_metric` — triggers `GEvalMetricWrapper`'s self-registration (depends on T004)
- [X] T007 [US1] Update `config/bots.yaml`: add `geval_criteria: "Response must stay formal and
  never promise a delivery date"` under `test_rag_bot` (sibling of its existing `metrics:` block),
  per contracts/evaluation-api.md's Configuration surface example — demonstrates opt-in activation
  for the quickstart manual check

**Checkpoint**: `g_eval` is registered, opt-in only, and fully testable independently of US2/US3.

---

## Phase 4: User Story 2 - Avaliar fluxos determinísticos com um grafo de decisão (DAG) (Priority: P2)

**Goal**: Register `DAGMetricWrapper` under the canonical name `dag`, available only when a bot's
`bots.yaml` entry declares `dag_builder` — a dotted path to a zero-argument callable that
`BotMetricConfigResolver` must *invoke* (the one divergence from `json_schema`'s as-is resolution,
research.md §R2) to obtain the `DeepAcyclicGraph`.

**Independent Test**: Configure a sample bot with a valid `dag_builder` dotted path, build an
`EvaluationContext` from a `NormalizedTrace` for that bot, run evaluation with `dag` in
`metric_names`, and confirm `EvaluationResult` contains a `dag` entry with score/threshold/status.

### Tests for User Story 2 ⚠️

> Write these tests FIRST, ensure they FAIL before implementation.

- [X] T008 [P] [US2] Write `tests/unit/evaluation/metrics/native/test_dag_metric.py`:
  `test_registered_under_canonical_name` (`MetricFactory._registry["dag"] is DAGMetricWrapper`),
  `test_wraps_native_dag_metric` (`DAGMetricWrapper._native_metric_cls is DAGMetric` from
  `deepeval.metrics`), and `test_dag_instance_forwarded_to_native_constructor`
  (`DAGMetricWrapper(threshold=0.5, deepeval_model=MagicMock(spec=DeepEvalBaseLLM),
  dag=MagicMock(spec=DeepAcyclicGraph))` constructs its native `DAGMetric` with that exact `dag`
  instance and a fixed literal `name`, data-model.md) — **implementation note**: real
  `DAGMetric.__init__` (installed `deepeval==4.0.7`) eagerly reads `dag.root_nodes`/`dag.multiturn`
  and deep-copies the graph (`copy_graph`), so a bare `spec=DeepAcyclicGraph` mock can't reach an
  `is`-identity assertion on `metric._native.dag`; the test instead patches
  `dag_metric.DAGMetric` and asserts the wrapper calls it with the exact `dag=` object, which
  verifies the same forwarding contract without depending on `DAGMetric`'s internal copy behavior
- [X] T009 [P] [US2] Update `tests/unit/evaluation/test_bot_metric_config_resolver.py`: add a
  module-level dummy zero-argument callable (e.g. `def build_dummy_dag() -> str: return
  "dag-instance-sentinel"`, mirroring the existing `DummySchema` real-importable-dummy pattern) to
  exercise the *invoked* resolution path; add `test_dag_appended_only_when_dag_builder_set` and
  `test_dag_omitted_when_dag_builder_absent` to `TestResolveMetricNames`; add
  `test_resolve_options_dag_invokes_resolved_callable_with_zero_args`
  (`resolve_options("test_bot", ["dag"])` with `bots.test_bot.dag_builder` stubbed to
  `f"{__name__}.build_dummy_dag"` returns `{"dag": {"dag": "dag-instance-sentinel"}}` — the
  **return value** of calling `build_dummy_dag()`, not the callable itself, unlike
  `test_json_correctness_resolves_expected_schema_via_dotted_path`'s as-is behavior),
  `test_dag_bad_module_path_propagates_import_error`, and
  `test_dag_bad_attribute_propagates_attribute_error` to `TestResolveOptions` (mirroring the
  existing `json_correctness` bad-path tests exactly, per research.md §R2)

### Implementation for User Story 2

- [X] T010 [US2] Implement `deepeval_platform/evaluation/metrics/native/dag_metric.py`:
  `DAGMetricWrapper(MetricBase)` with `_native_metric_cls = DAGMetric` (`from deepeval.metrics
  import DAGMetric`), `__init__(self, threshold: float, deepeval_model: DeepEvalBaseLLM, dag:
  DeepAcyclicGraph)` (`from deepeval.metrics.dag import DeepAcyclicGraph`) constructing
  `self._native = DAGMetric(name="Decision Graph", dag=dag, threshold=threshold,
  model=deepeval_model, async_mode=True)`, `@MetricFactory.register("dag")` — makes T008 pass
- [X] T011 [US2] Update `deepeval_platform/evaluation/bot_metric_config_resolver.py` (touches the
  same file as T005 — sequential, applied after it): in `resolve_metric_names`, append a check for
  `bots.{bot_id}.dag_builder` immediately after the new `g_eval` check, appending `"dag"`; in
  `resolve_options`, add `elif name == "dag": options[name] = self._resolve_dag_options(bot_id)`
  and a `_resolve_dag_options(self, bot_id)` method that mirrors
  `_resolve_json_correctness_options` exactly (`importlib.import_module` + `getattr` on the dotted
  path from `bots.{bot_id}.dag_builder`) but adds a trailing `()` to **invoke** the resolved
  attribute with zero arguments before returning `{"dag": <the invocation's return value>}`
  (research.md §R2 — the one resolver method in this project that calls its resolved attribute
  rather than using it as-is) — makes T009 pass
- [X] T012 [US2] Update `deepeval_platform/evaluation/metrics/native/__init__.py` (touches the same
  file as T006 — sequential, applied after it): add `dag_metric,  # noqa: F401` to the
  alphabetically-ordered import tuple, immediately before `faithfulness_metric` — triggers
  `DAGMetricWrapper`'s self-registration (depends on T010)

**Checkpoint**: `dag` is registered, opt-in only, and fully testable independently of US1/US3. No
`dag_builder` fixture is added to `config/bots.yaml` in this milestone — mirroring M3.3's own
`json_schema` precedent (no real importable dotted-path target exists in this codebase yet;
SC-006 explicitly makes that the bot operator's job, not this feature's).

---

## Phase 5: User Story 3 - Comparar respostas RAG contra métricas de referência do Ragas (Priority: P3)

**Goal**: Register `RagasMetricWrapper`-derived classes under `ragas_answer_correctness` and
`ragas_context_recall`, each opt-in per bot via `bots.<bot>.metrics.ragas_*.enabled`, backed by a
new `RagasLLMAdapter` (adapts the bot's existing `DeepEvalBaseLLM` judge — never LangChain,
Principle III) and the project's existing global embedding configuration for
`ragas_answer_correctness` only.

**Independent Test**: Enable both Ragas metrics for a sample RAG bot in `config/bots.yaml`, build
an `EvaluationContext` from a `NormalizedTrace` for that bot, run evaluation, and confirm
`EvaluationResult` contains `ragas_answer_correctness` and `ragas_context_recall` entries.

### Tests for User Story 3 ⚠️

> Write these tests FIRST, ensure they FAIL before implementation.

- [X] T013 [P] [US3] Write `tests/unit/llm/test_ragas_adapter.py`:
  `test_agenerate_text_delegates_to_deepeval_model_a_generate` (a `RagasLLMAdapter` wrapping a
  `MagicMock(spec=DeepEvalBaseLLM)` whose `a_generate` is an `AsyncMock` returning
  `("generated text", TokenUsage(...))`; `await adapter.agenerate_text(prompt=<PromptValue-like
  mock with .to_string() returning "the prompt">)` calls
  `deepeval_model.a_generate("the prompt")` and returns a Ragas `LLMResult` whose
  `generations[0][0].text == "generated text"`), `test_generate_text_sync_wrapper_delegates_to_a_generate`
  (the required sync ABC method produces the same shape via an event-loop-safe call, not on
  `RagasMetricWrapper.measure()`'s call path per data-model.md), `test_is_finished_always_returns_true`,
  and `test_source_does_not_import_llm_provider_factory_or_provider_classes` (a grep-style
  assertion, mirroring `TestNoMetricLogicImported` in `test_bot_metric_config_resolver.py`, that
  `deepeval_platform/llm/ragas_adapter.py`'s source contains no
  `from deepeval_platform.llm.factory import` and no
  `from deepeval_platform.llm.{anthropic,openai,openrouter}_provider import` — FR-009: must not
  alter `LLMProviderFactory` or any concrete provider)
- [X] T014 [P] [US3] Write `tests/unit/evaluation/metrics/native/test_ragas_metric.py`:
  `test_answer_correctness_registered_under_canonical_name` and
  `test_context_recall_registered_under_canonical_name` (each `MetricFactory._registry[name]` is a
  distinct `RagasMetricWrapper` subclass); `test_answer_correctness_constructs_llm_and_embeddings`
  (mocking `ragas.metrics.AnswerCorrectness`, `RagasLLMAdapter`, `langchain_openai.OpenAIEmbeddings`,
  and `ragas.embeddings.LangchainEmbeddingsWrapper`, plus a stubbed `ConfigManager` returning
  `embedding.model`/`embedding.dimensions`/`OPENAI_API_KEY`; constructing the
  `ragas_answer_correctness`-registered class asserts `OpenAIEmbeddings` was called with the
  stubbed `model=`/`api_key=` — same construction `QdrantVectorStoreProvider` uses, FR-014 — and
  `AnswerCorrectness` was called with `llm=<RagasLLMAdapter instance>,
  embeddings=<LangchainEmbeddingsWrapper instance>`); `test_context_recall_constructs_llm_only`
  (constructing the `ragas_context_recall`-registered class asserts `ContextRecall` was called with
  only `llm=...` and that no `OpenAIEmbeddings`/embedding config was read — FR-014 scopes
  embeddings to Answer Correctness only); `test_measure_builds_single_turn_sample_and_maps_score`
  (per metric, `context.trace` with `input`/`output`/`expected_output`/`context` set; mocked
  `single_turn_ascore` returns `0.83`; `await metric.measure(context)` builds a `SingleTurnSample`
  with the exact field mapping from data-model.md's table — `answer_correctness` reads
  `user_input`/`response`/`reference`; `context_recall` reads
  `user_input`/`reference`/`retrieved_contexts` — and returns `MetricResult(score=0.83,
  threshold=<the constructed threshold>, passed=(0.83 >= threshold), error=None)`);
  `test_threshold_and_passed_properties_reflect_plain_attributes` (no native `.threshold`/`.success`
  proxy exists, research.md §R4); and
  `test_native_metric_cls_exposes_threshold_default_of_0_5_for_orchestrator_fallback`
  (`inspect.signature(MetricFactory._registry["ragas_answer_correctness"]._native_metric_cls.__init__
  ).parameters["threshold"].default == 0.5` — guards the design gap noted above so
  `EvaluationOrchestrator._native_default_threshold` keeps resolving a numeric default for a bot
  that enables a Ragas metric without configuring its own threshold, with zero orchestrator change);
  and `test_constructor_raises_import_error_when_ragas_unavailable_without_breaking_registration`
  (monkeypatches `ragas_metric._RAGAS_IMPORT_ERROR` to a dummy `ImportError` instance, then asserts
  (a) `MetricFactory._registry["ragas_answer_correctness"]`/`["ragas_context_recall"]` are still
  present — registration itself never touched the guarded names, research.md §R5 — and
  (b) instantiating either registered class now raises `ImportError`, restoring the monkeypatched
  value afterward) — closes the I1 gap: proves a missing `ragas` install isolates to whichever
  Ragas metric a bot opts into, not a package-import-time crash of every metric
- [X] T015 [P] [US3] Update `tests/unit/evaluation/test_bot_metric_config_resolver.py` (touches the
  same file as T003/T009 — sequential, applied last of the three): add
  `test_ragas_answer_correctness_appended_when_enabled_truthy` (parametrized over the same truthy
  values as the existing `summarization` test),
  `test_ragas_answer_correctness_omitted_when_false_or_absent`,
  `test_ragas_context_recall_appended_when_enabled_truthy`,
  `test_ragas_context_recall_omitted_when_false_or_absent`, and
  `test_ragas_metrics_independent_opt_in` (enabling only one of the two appends exactly that one —
  spec Edge Cases) to `TestResolveMetricNames`; add
  `test_resolve_options_ragas_names_return_empty_dict` (`resolve_options("test_bot",
  ["ragas_answer_correctness", "ragas_context_recall"])` returns `{"ragas_answer_correctness": {},
  "ragas_context_recall": {}}` — the selector is fixed per canonical name at registration, not
  resolved per-bot, data-model.md) to `TestResolveOptions`; extend the existing
  `test_fixed_append_order_and_strategy_metrics_untouched` test to stub all four new M3.4 opt-in
  keys (`geval_criteria`, `dag_builder`, both `ragas_*.enabled`) alongside the existing four M3.3
  keys and assert the full fixed order from data-model.md: `[..., "summarization",
  "json_correctness", "prompt_alignment", "conversational_g_eval", "g_eval", "dag",
  "ragas_answer_correctness", "ragas_context_recall"]`

### Implementation for User Story 3

- [X] T016 [US3] Implement `deepeval_platform/llm/ragas_adapter.py`: `RagasLLMAdapter` implementing
  `ragas.llms.base.BaseRagasLLM`'s abstract surface — `__init__(self, deepeval_model:
  DeepEvalBaseLLM)` stores the wrapped judge; `async def agenerate_text(self, prompt, n=1,
  temperature=0.01, stop=None, callbacks=None)` calls `await
  self._deepeval_model.a_generate(prompt.to_string())` and wraps the returned string into Ragas'
  `LLMResult(generations=[[Generation(text=<the string>)]])`; `def generate_text(self, prompt, n=1,
  temperature=0.01, stop=None, callbacks=None)` is a thin sync wrapper (delegates to
  `self._deepeval_model.generate(prompt.to_string())`, same `LLMResult`/`Generation` wrapping —
  present only to satisfy the ABC, never called from `RagasMetricWrapper.measure()`'s async-only
  path); `def is_finished(self, response) -> bool: return True` (no partial/streaming-completion
  concept in this project's provider abstraction, research.md §R3) — makes T013 pass; does not
  import from `deepeval_platform.llm.factory` or any concrete provider module (FR-009)
- [X] T017 [US3] Implement `deepeval_platform/evaluation/metrics/native/ragas_metric.py`:
  - At module top: guard the `ragas.*` imports — `try: from ragas.dataset_schema import
    SingleTurnSample; from ragas.embeddings import LangchainEmbeddingsWrapper; from ragas.metrics
    import AnswerCorrectness, ContextRecall` / `except ImportError as exc:
    _RAGAS_IMPORT_ERROR = exc` (else `_RAGAS_IMPORT_ERROR = None`) — module import must succeed
    even when `ragas` is not installed, so T019's package-level import never raises
    (research.md §R5, resolves the I1 gap between FR-010/the Edge Case and the design)
  - A local `_RagasThresholdDefault` placeholder class with `def __init__(self, threshold: float =
    0.5) -> None: ...` — exists solely so `EvaluationOrchestrator._native_default_threshold`'s
    unmodified `inspect.signature(...).parameters["threshold"].default` lookup keeps working for
    a wrapper with no real native DeepEval class (see "A design gap closed during task
    generation" above)
  - `RagasMetricWrapper(MetricBase)` — **not itself decorated with `@MetricFactory.register`** —
    with `_native_metric_cls: ClassVar[type] = _RagasThresholdDefault`; `__init__(self, threshold:
    float, deepeval_model: DeepEvalBaseLLM, ragas_metric_name: Literal["answer_correctness",
    "context_recall"])` first checks `if _RAGAS_IMPORT_ERROR is not None: raise ImportError("ragas
    is not installed; run `uv sync`") from _RAGAS_IMPORT_ERROR` — before referencing any guarded
    name, so a missing install fails only this constructor call (surfaced inside
    `_measure_one`'s existing try/except, M3.1), never module import; otherwise builds `judge =
    RagasLLMAdapter(deepeval_model)`; when
    `ragas_metric_name == "answer_correctness"`, reads `embedding.model`/`embedding.dimensions`
    from `ConfigManager.instance()` (constructor-injected `config: ConfigManager | None = None`
    param, defaulting to `ConfigManager.instance()`, mirroring every other resolver/orchestrator
    class in this project) and `OPENAI_API_KEY`, builds `OpenAIEmbeddings(model=..., api_key=...)`
    (same construction `QdrantVectorStoreProvider` already uses, FR-014) wrapped in
    `ragas.embeddings.LangchainEmbeddingsWrapper`, and constructs
    `AnswerCorrectness(llm=judge, embeddings=wrapped_embeddings)`; when `"context_recall"`,
    constructs `ContextRecall(llm=judge)` with no embeddings step at all; stores the constructed
    metric as `self._ragas_metric`, `threshold` as `self._threshold`, `ragas_metric_name` as
    `self._ragas_metric_name`, and `self._passed: bool | None = None`
  - `threshold` property returns `self._threshold`; `passed` property returns `self._passed`
  - `async def measure(self, context: EvaluationContext) -> MetricResult` (overridden, does not
    call `super().measure()`): builds a `ragas.dataset_schema.SingleTurnSample` from
    `context.trace` — `user_input=trace.input`, `reference=trace.expected_output` always; plus
    `response=trace.output` when `self._ragas_metric_name == "answer_correctness"`, or
    `retrieved_contexts=list(trace.context)` when `"context_recall"` (data-model.md's field-mapping
    table); `score = await self._ragas_metric.single_turn_ascore(sample)`; sets `self._passed =
    score >= self._threshold`; returns `MetricResult(score=score, threshold=self._threshold,
    passed=self._passed, error=None)`
  - Two thin subclasses, each directly registered (not via `functools.partial` — see the design-gap
    note above for why): `@MetricFactory.register("ragas_answer_correctness")` on a
    `_AnswerCorrectnessMetricWrapper(RagasMetricWrapper)` whose `__init__(self, threshold,
    deepeval_model)` calls `super().__init__(threshold=threshold, deepeval_model=deepeval_model,
    ragas_metric_name="answer_correctness")`; `@MetricFactory.register("ragas_context_recall")` on
    a `_ContextRecallMetricWrapper(RagasMetricWrapper)` calling `super().__init__(...,
    ragas_metric_name="context_recall")` — both inherit `_native_metric_cls` from
    `RagasMetricWrapper`, satisfying `_native_default_threshold` unmodified
  - Makes T014 pass (depends on T016)
- [X] T018 [US3] Update `deepeval_platform/evaluation/bot_metric_config_resolver.py` (touches the
  same file as T005/T011 — sequential, applied last of the three): in `resolve_metric_names`,
  append the two independent truthy checks for `bots.{bot_id}.metrics.ragas_answer_correctness.enabled`
  and `bots.{bot_id}.metrics.ragas_context_recall.enabled` (same `_TRUTHY_VALUES` pattern as
  `summarization`), appending `"ragas_answer_correctness"` / `"ragas_context_recall"` independently,
  immediately after the new `dag` check (data-model.md's fixed append order); `resolve_options`
  needs no new branch for either name — both already fall through to the existing generic `else:
  options[name] = {}` (data-model.md: the selector is fixed per canonical name at registration, not
  resolved per-bot) — makes T015 pass
- [X] T019 [US3] Update `deepeval_platform/evaluation/metrics/native/__init__.py` (touches the same
  file as T006/T012 — sequential, applied last of the three): add `ragas_metric,  # noqa: F401` to
  the alphabetically-ordered import tuple, immediately before `role_adherence_metric` — triggers
  both `RagasMetricWrapper` subclasses' self-registration (depends on T017); this plain import is
  safe even when `ragas` isn't installed because T017's guard keeps `ragas_metric.py` itself
  import-clean (research.md §R5) — no try/except needed at this call site
- [X] T020 [US3] Update `config/bots.yaml` (touches the same file as T007, same `test_rag_bot`
  block — additive, non-conflicting): add
  ```yaml
      metrics:
        ragas_answer_correctness:
          enabled: true
        ragas_context_recall:
          enabled: true
  ```
  under `test_rag_bot`'s existing `metrics:` block (sibling of its existing `faithfulness`/
  `summarization` entries), per contracts/evaluation-api.md's Configuration surface example —
  demonstrates opt-in activation for the quickstart manual check; requires `uv sync` (T001) to have
  installed `ragas` for any real run against this bot

**Checkpoint**: All four new metrics (`g_eval`, `dag`, `ragas_answer_correctness`,
`ragas_context_recall`) are registered. Opt-in metrics resolve automatically only when a bot's
configuration declares the required key, and a bot declaring none of them is entirely unaffected.
All three user stories work independently and together.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Cross-story edge case coverage (spec.md Edge Cases) and final verification across all
three stories.

- [X] T021 [P] Update `tests/unit/evaluation/test_evaluation_orchestrator.py`: add
  `test_malformed_g_eval_criteria_isolated_not_blocking` (an empty-string `criteria` reaching
  `GEval.__init__`/`measure()` raises, driven through a real or fake-registered `g_eval` name
  alongside a sibling metric name in the same `evaluate()` call — asserts `g_eval`'s `MetricResult`
  is isolated-failed while the sibling completes normally, mirroring the existing
  `test_malformed_opt_in_config_isolated_not_blocking` pattern from M3.3), and
  `test_invalid_dag_definition_isolated_not_blocking` (a `dag_builder` resolution or `DAGMetric`
  construction/measure failure — cycle, orphan node, broken reference — isolates only `dag`'s
  `MetricResult`, sibling completes normally) — spec.md Edge Cases (first two bullets)
- [X] T022 Update `tests/unit/evaluation/test_evaluation_orchestrator.py` (touches the same file as
  T021 — sequential, applied after it): add
  `test_ragas_measure_exception_or_timeout_isolated_not_blocking` (a fake-registered
  `ragas_answer_correctness`/`ragas_context_recall` whose `measure()` raises, and a separate case
  where it exceeds the configured timeout via `asyncio.wait_for` — both isolate only that Ragas
  metric's `MetricResult`, sibling completes normally — spec.md Edge Cases, covers the
  "misconfigured" half of the scenario as an ordinary caught exception; the "not installed" half is
  covered at the unit level by T014's guarded-import test, per research.md §R5) and
  `test_all_four_new_metrics_enabled_simultaneously_run_independently` (a single `evaluate()` call
  requesting `g_eval`, `dag`, `ragas_answer_correctness`, and `ragas_context_recall` together, each
  fake-registered with distinct outcomes — one raising, one succeeding, etc. — asserts every
  `MetricResult` reflects only its own outcome, none blocks or waits on another, mirroring M3.3's
  own multi-opt-in isolation test) — spec.md Edge Cases (last two bullets), SC-004
- [X] T023 Run the full quickstart.md validation suite — `uv run pytest tests/unit/evaluation -v`,
  `uv run pytest tests/unit/llm/test_ragas_adapter.py -v`, and `uv run pytest
  --cov=deepeval_platform --cov-report=term-missing --cov-fail-under=80` — confirm every spec.md
  acceptance scenario and edge case in quickstart.md's mapping table passes (including all
  pre-existing M3.1-M3.3 isolation/duplicate/timeout tests, unaffected by this milestone) and
  overall coverage remains ≥ 80%; fix any gap found

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: T001 blocks only the Ragas-importing tasks (T013, T014, T017, T019, T020) —
  US1 (Phase 3) and US2 (Phase 4) can start immediately, in parallel with T001
- **Foundational (Phase 2)**: N/A — nothing blocks any user story beyond what already exists
- **User Story 1 (Phase 3)**: No dependency on Setup or any other story — independently
  implementable and testable first (MVP)
- **User Story 2 (Phase 4)**: No dependency on US1's wrapper *behavior*; shares sequential edit
  targets `bot_metric_config_resolver.py` (T005 → T011) and `native/__init__.py` (T006 → T012)
- **User Story 3 (Phase 5)**: Depends on T001 (Setup) for the `ragas` dependency; no dependency on
  US1/US2's wrapper *behavior*; shares sequential edit targets `bot_metric_config_resolver.py`
  (T005 → T011 → T018), `native/__init__.py` (T006 → T012 → T019), and
  `test_bot_metric_config_resolver.py` (T003 → T009 → T015)
- **Polish (Phase 6)**: T021/T022 can use fake-registered metric stubs (not the real US1/US2/US3
  wrapper classes), so they carry no genuine technical dependency on those stories being
  implemented first — the ordering below is a single-developer sequencing convenience (avoids
  motivating the tests before any real opt-in metric exists), matching M3.3's own Polish-phase
  precedent. T023 (full suite run) genuinely depends on all three stories being complete.

### Within Each User Story

- Tests written and failing before implementation, per constitution Principle IV (NON-NEGOTIABLE):
  T002-T003 before T004-T007; T008-T009 before T010-T012; T013-T015 before T016-T020
- Wrapper implementation before the `native/__init__.py` import that triggers self-registration
  (T004 before T006; T010 before T012; T016-T017 before T019)
- `RagasLLMAdapter` (T016) before `RagasMetricWrapper` (T017), which constructs it

### Parallel Opportunities

- T002 and T003 (US1, distinct test files) in parallel
- T008 and T009 (US2, distinct test files) in parallel
- T013, T014, and T015 (US3, distinct test files) in parallel
- T001 (Setup) can run in parallel with all of Phase 3 (US1) and Phase 4 (US2), since neither
  depends on `ragas` being installed
- Once each story's tests are written, US1, US2, and US3 could in principle be staffed in parallel
  by different developers — in practice all three share sequential edit targets
  (`bot_metric_config_resolver.py`, `native/__init__.py`, `test_bot_metric_config_resolver.py`) so
  a single-developer run should follow priority order (P1 → P2 → P3) to avoid merge conflicts

---

## Parallel Example: User Story 1

```bash
# Launch both User Story 1 test tasks together:
Task: "Write tests/unit/evaluation/metrics/native/test_g_eval_metric.py"
Task: "Update tests/unit/evaluation/test_bot_metric_config_resolver.py (geval_criteria cases)"
```

## Parallel Example: User Story 3

```bash
# Launch all three User Story 3 test tasks together:
Task: "Write tests/unit/llm/test_ragas_adapter.py"
Task: "Write tests/unit/evaluation/metrics/native/test_ragas_metric.py"
Task: "Update tests/unit/evaluation/test_bot_metric_config_resolver.py (ragas_*.enabled cases)"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (T001 — can run in parallel with Phase 3)
2. Complete Phase 3: User Story 1 (`g_eval`)
3. **STOP and VALIDATE**: `uv run pytest tests/unit/evaluation/metrics/native/test_g_eval_metric.py
   tests/unit/evaluation/test_bot_metric_config_resolver.py -v`
4. Deploy/demo if ready

### Incremental Delivery

1. Setup → Foundation ready (nothing to build, T001 only gates US3)
2. Add User Story 1 (`g_eval`) → Test independently → Deploy/Demo (MVP!)
3. Add User Story 2 (`dag`) → Test independently → Deploy/Demo
4. Add User Story 3 (`ragas_answer_correctness`/`ragas_context_recall`) → Test independently →
   Deploy/Demo
5. Each story adds value without breaking previous stories

### Parallel Team Strategy

With multiple developers:

1. One developer runs T001 (Setup) while two others start on US1/US2's test tasks in parallel
2. Once tests are written:
   - Developer A: User Story 1 implementation
   - Developer B: User Story 2 implementation
   - Developer C: User Story 3 implementation (blocked on T001 completing first)
3. Stories complete independently but coordinate on the three shared files
   (`bot_metric_config_resolver.py`, `native/__init__.py`, `test_bot_metric_config_resolver.py`) to
   avoid merge conflicts — apply in priority order (US1 → US2 → US3)

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Each user story is independently completable and testable
- Verify tests fail before implementing
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently
- `dag_builder` deliberately has no `config/bots.yaml` fixture in this milestone, mirroring
  `json_schema`'s M3.3 precedent (no real importable dotted-path target exists yet)

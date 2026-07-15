# Tasks: Quality/Safety + Conversational Metrics Integration

**Input**: Design documents from `/specs/006-quality-conversational-metrics/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/evaluation-api.md, quickstart.md

**Tests**: Included and REQUIRED — constitution Principle IV (TDD, NON-NEGOTIABLE) and plan.md's
Testing section mandate tests before implementation for every module in this milestone, enforced
by the existing `pytest-cov --cov-fail-under=80` gate.

**Organization**: Tasks are grouped by user story (spec.md priorities P1/P2/P3/P4) to enable
independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3, US4)
- File paths are exact and relative to the repository root

## Path Conventions

Single project (existing `deepeval_platform/` package + `tests/`), per plan.md's Project
Structure — no new top-level project, no new sub-package. All ten wrapper classes land in the
`deepeval_platform/evaluation/metrics/native/` sub-package M3.1/M3.2 already established.

---

## Phase 1: Setup (Shared Infrastructure)

**N/A** — no new package skeleton, dependency, or top-level directory is needed. Every new module
lands inside `deepeval_platform/evaluation/` (already exists) and its mirrored `tests/unit/evaluation/`
tree (already exists), exactly as M3.1/M3.2 left it.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The shared extension points every later user story needs — the new conversational
test-case base class (FR-002/FR-003), the backward-compatible `MetricFactory.create()`
generalization (FR-016), `ConfigManager`'s new list-flattening support (research.md §R4), and the
`BotMetricConfigResolver` (FR-015) that reads all five new `bots.yaml` keys and merges/resolves
options — plus wiring that resolver into `EvaluationOrchestrator` (FR-013). None of this contains
story-specific metric wrappers; each piece gets its own test first (TDD).

**⚠️ CRITICAL**: No user story work can begin until this phase is complete. This is intentionally
larger than M3.2's empty Foundational phase because M3.3's stories share a real design fork
(`ConversationalTestCase` vs. `LLMTestCase`) and a real new extension point (opt-in per-bot metric
options) that M3.1's base classes did not anticipate.

- [X] T001 [P] Write `tests/unit/evaluation/metrics/test_conversational_metric_base.py`: a concrete
  test subclass of `ConversationalMetricBase` setting `_native_metric_cls` to a mocked native
  `BaseConversationalMetric`; `measure(context)` builds a `ConversationalTestCase` from
  `context.trace.messages` mapped to `Turn(role=m.role, content=m.content)` objects (data-model.md),
  passes an optional `chatbot_role` through to the test case when given, awaits
  `a_measure(test_case, _show_indicator=False)`, and returns a `MetricResult`; `threshold`/`passed`
  properties proxy the native metric exactly like `MetricBase`; a `Turn(role="system", ...)` (or any
  role outside `{"user", "assistant"}`) raises a pydantic `ValidationError` when the test case is
  built, and that exception propagates out of `measure()` uncaught (isolation stays the
  orchestrator's job, research.md §R2) — no bespoke role-validation code exercised or expected
- [X] T002 Implement `deepeval_platform/evaluation/metrics/conversational_metric_base.py`:
  `ConversationalMetricBase` ABC (sibling to `MetricBase`, NOT a subclass — research.md §R8) with
  `_native_metric_cls: ClassVar[type[BaseConversationalMetric]]`,
  `__init__(threshold, deepeval_model)` constructing `self._native`, `threshold`/`passed`
  properties, `_build_test_case(trace, chatbot_role=None)` static method building
  `ConversationalTestCase(turns=[Turn(role=m.role, content=m.content) for m in trace.messages],
  chatbot_role=chatbot_role)`, and `async def measure(context)` — makes T001 pass (depends on
  `deepeval_platform.evaluation.evaluation_context.EvaluationContext` and
  `deepeval_platform.evaluation.evaluation_result.MetricResult`, both unchanged since M3.1)
- [X] T003 [P] Update `tests/unit/evaluation/metrics/test_metric_factory.py`: add
  `test_create_forwards_generic_options_to_wrapper` (a dummy `MetricBase` subclass whose `__init__`
  accepts an extra keyword-only param; `MetricFactory.create(name, threshold=..., deepeval_model=...,
  extra_kwarg="value")` passes `extra_kwarg` straight through) and
  `test_create_with_no_extra_options_matches_existing_signature` (every existing M3.1/M3.2-style
  call — `threshold` and `deepeval_model` only — still succeeds unchanged, FR-016)
- [X] T004 Implement `deepeval_platform/evaluation/metrics/metric_factory.py`: change
  `create()`'s signature to
  `create(cls, name: str, *, threshold: float, deepeval_model: DeepEvalBaseLLM, **options: object) ->
  MetricBase`, forwarding `**options` into `cls._registry[name](threshold=threshold,
  deepeval_model=deepeval_model, **options)` with zero branching on `name` (FR-016, research.md
  §R7) — makes T003 pass; `register()` and `_registry` unchanged (SC-006)
- [X] T005 [P] Update `tests/unit/config/test_config_manager.py`: add
  `test_yaml_list_value_flattened_into_indexed_keys` (a YAML list like `prompt_instructions: ["Be
  concise", "Use bullet points"]` under a nested key produces two flat entries,
  `<key>.0 == "Be concise"` and `<key>.1 == "Use bullet points"`, retrievable via
  `cfg.get("<key>.0")`) and `test_yaml_scalar_and_dict_values_unaffected_by_list_branch` (existing
  scalar/nested-dict keys still flatten exactly as before — regression guard, research.md §R4)
- [X] T006 Implement `deepeval_platform/config/config_manager.py`
  (`_flatten_yaml`): add a `list` branch — when `v` is a `list`, recurse into each element under
  `f"{flat_key}.{i}"` (reusing the same `dict`/scalar recursion, no new public method); the existing
  `dict` and scalar/`else` branches are untouched — makes T005 pass
- [X] T007 [P] Write `tests/unit/evaluation/test_bot_metric_config_resolver.py`:
  `resolve_metric_names(bot_id, strategy_metrics)` returns `strategy_metrics` unchanged when the
  bot declares none of the four opt-in keys (FR-011); appends `"summarization"` when
  `bots.<bot>.metrics.summarization.enabled` reads as one of `{"true", "1", "yes"}`
  case-insensitively (research.md §R6) and omits it for `"false"`/absent; appends
  `"json_correctness"` only when `bots.<bot>.json_schema` is set, `"prompt_alignment"` only when at
  least `bots.<bot>.prompt_instructions.0` is set, and `"conversational_g_eval"` only when
  `bots.<bot>.conversational_geval_criteria` is set — always in that fixed append order, and never
  reordering/removing entries already in `strategy_metrics`;
  `resolve_options(bot_id, metric_names)` returns `{}` for every name needing no extra kwargs;
  resolves `json_correctness` to `{"expected_schema": <class>}` via
  `importlib.import_module`+`getattr` on `bots.<bot>.json_schema` (a dotted path constructed from a
  real importable dummy `BaseModel` defined in this test module, per research.md §R5) and lets a
  bad path's `ImportError`/`AttributeError` propagate uncaught; resolves `prompt_alignment` to
  `{"prompt_instructions": [...]}` by probing `bots.<bot>.prompt_instructions.0`, `.1`, ... until
  absent; resolves `conversational_g_eval` to `{"criteria": <string>}`; resolves `role_adherence`
  (whenever present in `metric_names`, regardless of `resolve_metric_names`'s opt-in tail) to
  `{"chatbot_role": <string or None>}`, `None` when `bots.<bot>.chatbot_role` is absent (FR-010a —
  never excluded, unlike the four opt-in names); a module-level grep-style assertion that
  `deepeval_platform/evaluation/bot_metric_config_resolver.py`'s source contains no
  `from deepeval_platform.evaluation.metrics` import (FR-015 — no metric instantiation/evaluation
  logic)
- [X] T008 Implement `deepeval_platform/evaluation/bot_metric_config_resolver.py`:
  `BotMetricConfigResolver` reading exclusively through `ConfigManager` (constructor accepts an
  optional injected `ConfigManager`, defaulting to `ConfigManager.instance()`, mirroring
  `EvaluationOrchestrator`'s pattern) with `resolve_metric_names(bot_id, strategy_metrics) ->
  list[str]` and `resolve_options(bot_id, metric_names) -> dict[str, dict[str, object]]` exactly
  per data-model.md's two tables — makes T007 pass (depends on T006 for the indexed
  `prompt_instructions` reads)
- [X] T009 [P] Update `tests/unit/evaluation/test_evaluation_orchestrator.py`: add
  `test_resolved_options_forwarded_to_metric_factory` (a fake registered wrapper whose `__init__`
  records any extra kwarg it receives; a `BotMetricConfigResolver` stub whose `resolve_options(bot_id,
  [name])` — called once per metric name, per data-model.md §"Modified: EvaluationOrchestrator" —
  returns `{"target_metric": {"extra": "value"}}` when called for the target name and `{other_name:
  {}}` when called for any other name; asserts `MetricFactory.create` is called with `extra="value"`
  for the target name and with no extra kwargs for every other requested name) and
  `test_no_configured_options_matches_byte_identical_prior_behavior` (a resolver stub returning `{}`
  for every name — every existing M3.1/M3.2 assertion in this file keeps passing unmodified,
  confirming the integration is purely additive, SC-006)
- [X] T010 Implement `deepeval_platform/evaluation/evaluation_orchestrator.py`:
  `EvaluationOrchestrator.__init__` gains an optional injected `BotMetricConfigResolver` (default
  `BotMetricConfigResolver()`), stored as `self._resolver`. `evaluate()` performs no options
  resolution itself — inside `_measure_one`'s existing `try` block, immediately before
  `MetricFactory.create`, add `options = self._resolver.resolve_options(bot_id, [name])[name]` and
  forward it as `MetricFactory.create(name, threshold=..., deepeval_model=..., **options)`, so any
  exception `resolve_options` raises (e.g. a malformed `json_schema` dotted path) is caught by the
  same `except Exception` that already isolates `MetricFactory.create`/`measure()` failures into a
  per-metric `MetricResult(error=...)` — do **not** call `resolve_options` in `evaluate()`'s
  pre-flight `ConfigResolutionError`-guarded block (that block's abort-the-whole-call semantics are
  reserved for threshold/timeout/judge misconfiguration; see data-model.md §"Modified:
  EvaluationOrchestrator"). Public signature of `evaluate(trace, bot_id, metric_names)` stays
  unchanged (FR-013, research.md §R3) — makes T009 pass (depends on T008, T004)

**Checkpoint**: `ConversationalMetricBase`, the generalized `MetricFactory.create()`, list-capable
`ConfigManager`, `BotMetricConfigResolver`, and option-forwarding `EvaluationOrchestrator` all exist
and are independently unit-tested. Every existing M3.1/M3.2 test still passes unmodified (options
resolve to `{}` when nothing is configured). User story implementation can now begin.

---

## Phase 3: User Story 1 - Fechar lacunas já declaradas de completude e relevância conversacional (Priority: P1) 🎯 MVP

**Goal**: Register `ConversationCompletenessMetricWrapper` and `ConversationRelevancyMetricWrapper`
under the canonical names `conversation_completeness` and `turn_relevancy` — the two names
`ConversationStrategy.get_metrics()` has declared since M2.1 but never resolved — so every
conversational-bot evaluation stops failing with an unknown-metric error.

**Independent Test**: Build an `EvaluationContext` from a sample conversational `NormalizedTrace`
(multi-turn `messages`) and `ConversationStrategy().get_metrics()` (unchanged by this story — the
two names are already declared), run the evaluation flow, and confirm the resulting
`EvaluationResult` contains `conversation_completeness` and `turn_relevancy` entries, each with a
score and pass/fail status.

### Tests for User Story 1 ⚠️

> Write these tests FIRST, ensure they FAIL before implementation.

- [X] T011 [P] [US1] Write
  `tests/unit/evaluation/metrics/native/test_conversation_completeness_metric.py`:
  `test_registered_under_canonical_name`
  (`MetricFactory._registry["conversation_completeness"] is ConversationCompletenessMetricWrapper`)
  and `test_wraps_native_conversation_completeness_metric`
  (`ConversationCompletenessMetricWrapper._native_metric_cls is ConversationCompletenessMetric`
  from `deepeval.metrics`) and `test_is_conversational_metric_base_subclass`
- [X] T012 [P] [US1] Write
  `tests/unit/evaluation/metrics/native/test_conversation_relevancy_metric.py`:
  `test_registered_under_canonical_name`
  (`MetricFactory._registry["turn_relevancy"] is ConversationRelevancyMetricWrapper` — FR-005, the
  canonical name matches what `ConversationStrategy.get_metrics()` already references, not a
  literal `"conversation_relevancy"`) and `test_wraps_native_turn_relevancy_metric`
  (`ConversationRelevancyMetricWrapper._native_metric_cls is TurnRelevancyMetric` from
  `deepeval.metrics` — DeepEval has no class literally named `ConversationalRelevancyMetric`)

### Implementation for User Story 1

- [X] T013 [US1] Implement
  `deepeval_platform/evaluation/metrics/native/conversation_completeness_metric.py`:
  `ConversationCompletenessMetricWrapper(ConversationalMetricBase)` with `_native_metric_cls =
  ConversationCompletenessMetric` (`deepeval.metrics`),
  `@MetricFactory.register("conversation_completeness")` — no `__init__` override needed, no extra
  constructor kwargs (data-model.md) — makes T011 pass (depends on T002, T004)
- [X] T014 [US1] Implement
  `deepeval_platform/evaluation/metrics/native/conversation_relevancy_metric.py`:
  `ConversationRelevancyMetricWrapper(ConversationalMetricBase)` with `_native_metric_cls =
  TurnRelevancyMetric` (`deepeval.metrics`), `@MetricFactory.register("turn_relevancy")` — makes
  T012 pass (depends on T002, T004)
- [X] T015 [US1] Update `deepeval_platform/evaluation/metrics/native/__init__.py`: add
  `conversation_completeness_metric,  # noqa: F401` and `conversation_relevancy_metric,  # noqa:
  F401` to the existing alphabetically-ordered import tuple so importing this package triggers both
  wrappers' self-registration (depends on T013, T014)

**Checkpoint**: User Story 1 is fully functional and independently testable —
`MetricFactory.create("conversation_completeness"/"turn_relevancy", ...)` resolves, and the
existing (unchanged) `tests/unit/evaluation/test_conversation_strategy.py` continues to assert
`ConversationStrategy.get_metrics() == ["conversation_completeness", "turn_relevancy"]`, now backed
by real registered wrappers end-to-end.

---

## Phase 4: User Story 2 - Detectar viés e conteúdo tóxico em qualquer tipo de bot (Priority: P2)

**Goal**: Register `BiasMetricWrapper` and `ToxicityMetricWrapper` under `bias`/`toxicity` and add
both names to `RAGStrategy.get_metrics()`, `AgentStrategy.get_metrics()`, and
`ConversationStrategy.get_metrics()` so every bot evaluation, regardless of type, gets this
cross-cutting safety check automatically.

**Independent Test**: Build an `EvaluationContext` from a sample `NormalizedTrace` of any bot type
and the corresponding strategy's `get_metrics()`, run the evaluation flow, and confirm
`EvaluationResult` contains `bias` and `toxicity` entries in all three cases, alongside each
strategy's pre-existing metrics.

### Tests for User Story 2 ⚠️

> Write these tests FIRST, ensure they FAIL before implementation.

- [X] T016 [P] [US2] Write `tests/unit/evaluation/metrics/native/test_bias_metric.py`:
  `test_registered_under_canonical_name` (`MetricFactory._registry["bias"] is BiasMetricWrapper`)
  and `test_wraps_native_bias_metric` (`BiasMetricWrapper._native_metric_cls is BiasMetric` from
  `deepeval.metrics`) and `test_is_metric_base_subclass` (LLMTestCase-based, not conversational)
- [X] T017 [P] [US2] Write `tests/unit/evaluation/metrics/native/test_toxicity_metric.py`:
  `test_registered_under_canonical_name`
  (`MetricFactory._registry["toxicity"] is ToxicityMetricWrapper`) and
  `test_wraps_native_toxicity_metric` (`ToxicityMetricWrapper._native_metric_cls is ToxicityMetric`
  from `deepeval.metrics`)
- [X] T018 [P] [US2] Update `tests/unit/evaluation/test_rag_strategy.py`:
  `test_contains_expected_metric_names` now asserts the eight-entry list `["answer_relevancy",
  "faithfulness", "contextual_precision", "contextual_recall", "contextual_relevancy",
  "hallucination", "bias", "toxicity"]` — same assertion, extended by two additive entries (the six
  existing entries keep their content and order, spec.md Edge Cases)
- [X] T019 [P] [US2] Update `tests/unit/evaluation/test_agent_strategy.py`:
  `test_contains_expected_metric_names` (add if not already present, mirroring
  `test_rag_strategy.py`'s pattern) asserts the four-entry list `["tool_correctness",
  "task_completion", "bias", "toxicity"]`
- [X] T020 [P] [US2] Update `tests/unit/evaluation/test_conversation_strategy.py`:
  `test_contains_expected_metric_names` now asserts the four-entry list
  `["conversation_completeness", "turn_relevancy", "bias", "toxicity"]` (the two existing entries
  keep their position; `knowledge_retention`/`role_adherence` are added later by US3)

### Implementation for User Story 2

- [X] T021 [US2] Implement `deepeval_platform/evaluation/metrics/native/bias_metric.py`:
  `BiasMetricWrapper(MetricBase)` with `_native_metric_cls = BiasMetric` (`deepeval.metrics`),
  `@MetricFactory.register("bias")` — no `_build_test_case` override needed (operates on
  `input`/`actual_output`, already populated by `MetricBase._build_test_case`) — makes T016 pass
  (depends on T004)
- [X] T022 [US2] Implement `deepeval_platform/evaluation/metrics/native/toxicity_metric.py`:
  `ToxicityMetricWrapper(MetricBase)` with `_native_metric_cls = ToxicityMetric`
  (`deepeval.metrics`), `@MetricFactory.register("toxicity")` — makes T017 pass (depends on T004)
- [X] T023 [US2] Update `deepeval_platform/evaluation/metrics/native/__init__.py`: add
  `bias_metric,  # noqa: F401` and `toxicity_metric,  # noqa: F401` to the existing
  alphabetically-ordered import tuple (depends on T021, T022; touches the same file as T015 —
  sequential, either order)
- [X] T024 [US2] Update `deepeval_platform/evaluation/strategies/rag_strategy.py`: append
  `"bias"`, `"toxicity"` as the seventh and eighth entries returned by `RAGStrategy.get_metrics()`
  — makes T018 pass (research.md: pure additive change, no other member changes)
- [X] T025 [US2] Update `deepeval_platform/evaluation/strategies/agent_strategy.py`: append
  `"bias"`, `"toxicity"` as the third and fourth entries returned by `AgentStrategy.get_metrics()`
  — makes T019 pass
- [X] T026 [US2] Update `deepeval_platform/evaluation/strategies/conversation_strategy.py`: append
  `"bias"`, `"toxicity"` as the third and fourth entries returned by
  `ConversationStrategy.get_metrics()` — makes T020 pass

**Checkpoint**: `bias`/`toxicity` resolve via `MetricFactory` and run automatically across all three
strategies. User Stories 1 AND 2 both work independently; `ConversationStrategy` now returns four
working names.

---

## Phase 5: User Story 3 - Aprofundar avaliação de qualidade conversacional (Priority: P3)

**Goal**: Register `KnowledgeRetentionMetricWrapper` and `RoleAdherenceMetricWrapper` under
`knowledge_retention`/`role_adherence` and add both to `ConversationStrategy.get_metrics()`, so
every conversational-bot evaluation automatically also checks multi-turn information retention and
persona adherence. `role_adherence` sources its `chatbot_role` from the optional `bots.yaml` key
(FR-010a) via the `BotMetricConfigResolver`/`EvaluationOrchestrator` plumbing built in Phase 2; its
absence isolates only that one metric, it does not exclude it.

**Independent Test**: Build an `EvaluationContext` from a multi-turn conversational
`NormalizedTrace` and `ConversationStrategy().get_metrics()`, run the evaluation flow, and confirm
`EvaluationResult` contains `knowledge_retention` and `role_adherence` entries alongside the four
entries already produced by User Stories 1 and 2 — without the caller requesting them explicitly.

### Tests for User Story 3 ⚠️

> Write these tests FIRST, ensure they FAIL before implementation.

- [X] T027 [P] [US3] Write
  `tests/unit/evaluation/metrics/native/test_knowledge_retention_metric.py`:
  `test_registered_under_canonical_name`
  (`MetricFactory._registry["knowledge_retention"] is KnowledgeRetentionMetricWrapper`) and
  `test_wraps_native_knowledge_retention_metric`
  (`KnowledgeRetentionMetricWrapper._native_metric_cls is KnowledgeRetentionMetric` from
  `deepeval.metrics`)
- [X] T028 [P] [US3] Write `tests/unit/evaluation/metrics/native/test_role_adherence_metric.py`:
  `test_registered_under_canonical_name`
  (`MetricFactory._registry["role_adherence"] is RoleAdherenceMetricWrapper`) and
  `test_wraps_native_role_adherence_metric`
  (`RoleAdherenceMetricWrapper._native_metric_cls is RoleAdherenceMetric` from `deepeval.metrics`)
  and `test_chatbot_role_forwarded_to_test_case` (constructing
  `RoleAdherenceMetricWrapper(threshold=0.5, deepeval_model=<mock>, chatbot_role="A polite banking
  assistant")` and calling `measure()` builds a `ConversationalTestCase` whose `chatbot_role`
  equals the value passed in — assert via a mocked `_native_metric_cls.a_measure` capturing its
  argument) and `test_missing_chatbot_role_defaults_to_none` (constructed with no `chatbot_role`
  kwarg, the built test case's `chatbot_role is None` — FR-010a, letting the native metric's own
  `MissingTestCaseParamsError` surface uncaught, per research.md §R1)
- [X] T029 [P] [US3] Update `tests/unit/evaluation/test_conversation_strategy.py`:
  `test_contains_expected_metric_names` now asserts the six-entry list
  `["conversation_completeness", "turn_relevancy", "bias", "toxicity", "knowledge_retention",
  "role_adherence"]` (touches the same file as T020 — sequential, applied after it)
- [X] T030 [P] [US3] Update `tests/unit/evaluation/test_evaluation_orchestrator.py`: add
  `test_role_adherence_missing_chatbot_role_isolated_not_skipped` — a fake registered
  `role_adherence` wrapper whose `measure()` raises the real DeepEval `MissingTestCaseParamsError`
  when constructed with `chatbot_role=None` (mirrors `TestMetricExceptionIsolated`'s pattern);
  asserts the resulting `MetricResult` has `score is None`, `passed is False`, and an `error`
  naming `MissingTestCaseParamsError`, while a sibling metric requested in the same call (e.g.
  `bias`) still completes with `passed is True` in the same `EvaluationResult` — FR-008/FR-010a,
  Edge Cases

### Implementation for User Story 3

- [X] T031 [US3] Implement
  `deepeval_platform/evaluation/metrics/native/knowledge_retention_metric.py`:
  `KnowledgeRetentionMetricWrapper(ConversationalMetricBase)` with `_native_metric_cls =
  KnowledgeRetentionMetric` (`deepeval.metrics`), `@MetricFactory.register("knowledge_retention")`
  — no `__init__` override, no extra kwargs — makes T027 pass (depends on T002, T004)
- [X] T032 [US3] Implement `deepeval_platform/evaluation/metrics/native/role_adherence_metric.py`:
  `RoleAdherenceMetricWrapper(ConversationalMetricBase)` with `_native_metric_cls =
  RoleAdherenceMetric` (`deepeval.metrics`), an `__init__(self, threshold, deepeval_model,
  chatbot_role: str | None = None)` storing `chatbot_role` and calling
  `super().__init__(threshold, deepeval_model)`, and a `measure()` override (or a
  `_build_test_case` override taking the stored `chatbot_role`) that forwards
  `chatbot_role=self._chatbot_role` into `ConversationalMetricBase._build_test_case`,
  `@MetricFactory.register("role_adherence")` — makes T028 pass (depends on T002, T004)
- [X] T033 [US3] Update `deepeval_platform/evaluation/metrics/native/__init__.py`: add
  `knowledge_retention_metric,  # noqa: F401` and `role_adherence_metric,  # noqa: F401` to the
  existing alphabetically-ordered import tuple (depends on T031, T032; touches the same file as
  T023 — sequential)
- [X] T034 [US3] Update `deepeval_platform/evaluation/strategies/conversation_strategy.py`: append
  `"knowledge_retention"`, `"role_adherence"` as the fifth and sixth entries returned by
  `ConversationStrategy.get_metrics()` — makes T029 pass (touches the same file as T026 —
  sequential, applied after it)

**Checkpoint**: `ConversationStrategy.get_metrics()` now returns all six working names.
`knowledge_retention`/`role_adherence` run automatically; a bot without `chatbot_role` configured
still gets `role_adherence` attempted and isolated-failed rather than silently skipped. User
Stories 1, 2, AND 3 all work independently.

---

## Phase 6: User Story 4 - Ativar métricas de qualidade sob demanda por bot (Priority: P4)

**Goal**: Register `SummarizationMetricWrapper`, `JsonCorrectnessMetricWrapper`,
`PromptAlignmentMetricWrapper`, and `ConversationalGEvalMetricWrapper` under
`summarization`/`json_correctness`/`prompt_alignment`/`conversational_g_eval`, available only when
a bot's `bots.yaml` entry opts in via the keys `BotMetricConfigResolver` already reads (built in
Phase 2) — no `EvaluationStrategy`'s automatic `get_metrics()` list changes for this story.

**Independent Test**: Configure a sample bot with `bots.<bot>.metrics.summarization.enabled: true`
or with `json_schema`/`prompt_instructions`/`conversational_geval_criteria`, run the evaluation
with `BotMetricConfigResolver.resolve_metric_names(...)`'s output as `metric_names`, and confirm
`EvaluationResult` includes the corresponding metric entry — while a bot declaring none of these
keys is entirely unaffected (no attempt, no error).

### Tests for User Story 4 ⚠️

> Write these tests FIRST, ensure they FAIL before implementation.

- [X] T035 [P] [US4] Write `tests/unit/evaluation/metrics/native/test_summarization_metric.py`:
  `test_registered_under_canonical_name`
  (`MetricFactory._registry["summarization"] is SummarizationMetricWrapper`) and
  `test_wraps_native_summarization_metric`
  (`SummarizationMetricWrapper._native_metric_cls is SummarizationMetric` from `deepeval.metrics`)
- [X] T036 [P] [US4] Write `tests/unit/evaluation/metrics/native/test_json_correctness_metric.py`:
  `test_registered_under_canonical_name`
  (`MetricFactory._registry["json_correctness"] is JsonCorrectnessMetricWrapper`),
  `test_wraps_native_json_correctness_metric`
  (`JsonCorrectnessMetricWrapper._native_metric_cls is JsonCorrectnessMetric` from
  `deepeval.metrics`), and `test_expected_schema_forwarded_to_native_constructor`
  (`JsonCorrectnessMetricWrapper(threshold=0.5, deepeval_model=<mock>,
  expected_schema=<dummy BaseModel subclass>)` constructs its native metric with that exact
  `expected_schema`)
- [X] T037 [P] [US4] Write `tests/unit/evaluation/metrics/native/test_prompt_alignment_metric.py`:
  `test_registered_under_canonical_name`
  (`MetricFactory._registry["prompt_alignment"] is PromptAlignmentMetricWrapper`),
  `test_wraps_native_prompt_alignment_metric`
  (`PromptAlignmentMetricWrapper._native_metric_cls is PromptAlignmentMetric` from
  `deepeval.metrics`), and `test_prompt_instructions_forwarded_to_native_constructor`
  (`PromptAlignmentMetricWrapper(threshold=0.5, deepeval_model=<mock>,
  prompt_instructions=["Always respond in JSON"])` constructs its native metric with that exact
  list)
- [X] T038 [P] [US4] Write
  `tests/unit/evaluation/metrics/native/test_conversational_g_eval_metric.py`:
  `test_registered_under_canonical_name`
  (`MetricFactory._registry["conversational_g_eval"] is ConversationalGEvalMetricWrapper`),
  `test_wraps_native_conversational_g_eval`
  (`ConversationalGEvalMetricWrapper._native_metric_cls is ConversationalGEval` from
  `deepeval.metrics`), `test_is_conversational_metric_base_subclass`, and
  `test_criteria_forwarded_to_native_constructor`
  (`ConversationalGEvalMetricWrapper(threshold=0.5, deepeval_model=<mock>, criteria="Stays
  on-topic")` constructs its native `ConversationalGEval` with `criteria="Stays on-topic"` and a
  fixed literal `name` — data-model.md notes `name` is not bot-configurable this milestone)
- [X] T039 [P] [US4] Update `tests/unit/evaluation/test_evaluation_orchestrator.py`: add two tests.
  (1) `test_malformed_opt_in_config_isolated_not_blocking` — a `BotMetricConfigResolver` stub whose
  `resolve_options(bot_id, [name])` raises (`ImportError`/`AttributeError`, mirroring a bad dotted
  `json_schema` import path, research.md §R5) only when called for `"json_correctness"` and returns
  `{}` for every other requested name, driven through `evaluate(trace, bot_id, ["json_correctness",
  "<sibling_name>"])` (a mixed `metric_names` list) — asserts `evaluate()` does **not** raise
  `ConfigResolutionError` (i.e. `resolve_options` failures do not hit the pre-flight
  threshold/timeout/judge abort path), the resulting `MetricResult` for `"json_correctness"` has
  `score is None`, `passed is False`, and a populated `error`, while the sibling metric's own
  `MetricResult` completes normally in the same call — this is the actual integration path
  described in spec.md's Edge Cases and data-model.md §"Modified: EvaluationOrchestrator", not
  merely a `MetricFactory.create`-time failure. (2) add
  `test_metric_wrapper_construction_failure_isolated_not_blocking` — a fake registered
  `json_correctness` wrapper whose `__init__` raises directly (resolver stub returns `{}`) —
  asserting the pre-existing `MetricFactory.create`/`measure()` isolation path (already covered by
  `_measure_one`'s `except Exception`) still holds independently of `resolve_options` — Edge Cases,
  spec.md; SC-005

### Implementation for User Story 4

- [X] T040 [US4] Implement `deepeval_platform/evaluation/metrics/native/summarization_metric.py`:
  `SummarizationMetricWrapper(MetricBase)` with `_native_metric_cls = SummarizationMetric`
  (`deepeval.metrics`), `@MetricFactory.register("summarization")` — no `__init__` override, no
  extra kwargs (research.md §R1: `n`/`assessment_questions` stay at native defaults) — makes T035
  pass (depends on T004)
- [X] T041 [US4] Implement
  `deepeval_platform/evaluation/metrics/native/json_correctness_metric.py`:
  `JsonCorrectnessMetricWrapper(MetricBase)` with `_native_metric_cls = JsonCorrectnessMetric`
  (`deepeval.metrics`), an `__init__(self, threshold, deepeval_model, expected_schema: type)`
  constructing `self._native = JsonCorrectnessMetric(threshold=threshold, model=deepeval_model,
  expected_schema=expected_schema, async_mode=True)`, `@MetricFactory.register("json_correctness")`
  — makes T036 pass (depends on T004)
- [X] T042 [US4] Implement
  `deepeval_platform/evaluation/metrics/native/prompt_alignment_metric.py`:
  `PromptAlignmentMetricWrapper(MetricBase)` with `_native_metric_cls = PromptAlignmentMetric`
  (`deepeval.metrics`), an `__init__(self, threshold, deepeval_model, prompt_instructions:
  list[str])` constructing `self._native = PromptAlignmentMetric(threshold=threshold,
  model=deepeval_model, prompt_instructions=prompt_instructions, async_mode=True)`,
  `@MetricFactory.register("prompt_alignment")` — makes T037 pass (depends on T004)
- [X] T043 [US4] Implement
  `deepeval_platform/evaluation/metrics/native/conversational_g_eval_metric.py`:
  `ConversationalGEvalMetricWrapper(ConversationalMetricBase)` with `_native_metric_cls =
  ConversationalGEval` (`deepeval.metrics`), an `__init__(self, threshold, deepeval_model,
  criteria: str)` constructing `self._native = ConversationalGEval(name="Conversational Quality",
  criteria=criteria, threshold=threshold, model=deepeval_model, async_mode=True)`,
  `@MetricFactory.register("conversational_g_eval")` — makes T038 pass (depends on T002, T004)
- [X] T044 [US4] Update `deepeval_platform/evaluation/metrics/native/__init__.py`: add
  `summarization_metric,  # noqa: F401`, `json_correctness_metric,  # noqa: F401`,
  `prompt_alignment_metric,  # noqa: F401`, and `conversational_g_eval_metric,  # noqa: F401` to
  the existing alphabetically-ordered import tuple (depends on T040–T043; touches the same file as
  T033 — sequential)
- [X] T045 [US4] Update `config/bots.yaml`: add example opt-in keys demonstrating activation, on
  bots other than where doing so would defeat another deliberate fixture property — e.g. add
  `metrics.summarization.enabled: true` under `test_rag_bot` (sibling of its existing
  `metrics.faithfulness.threshold`), `prompt_instructions` under `test_agent_bot`, and
  `conversational_geval_criteria` under `test_conversation_bot` (alongside its existing `messages`
  field mapping and its deliberately-absent `chatbot_role`), per contracts/evaluation-api.md's
  Configuration surface example. `conversational_geval_criteria` must NOT go on `test_agent_bot`:
  that bot's `field_mapping` has no `messages` entry, so `NormalizedTrace.messages` defaults to
  `[]` there and every conversational metric — including `conversational_g_eval` — would hit the
  isolated-failure path on every run, never demonstrating a passing opt-in result (spec.md's Edge
  Cases on empty `messages`). `json_schema` is left undocumented in this fixture (no real
  importable dummy schema class exists in the project) to avoid a fixture pointing at a
  non-existent path — `json_correctness`'s opt-in path is exercised purely at the unit level (T036,
  T007)

**Checkpoint**: All ten M3.3 metrics are now registered. Opt-in metrics resolve automatically only
when a bot's configuration declares the required key, and a bot declaring none of them is entirely
unaffected. All four user stories work independently and together.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Cross-story edge case coverage and final verification across all four stories.

- [X] T046 [P] Update `tests/unit/evaluation/test_evaluation_orchestrator.py`: add
  `test_invalid_message_role_isolates_only_conversational_metrics` — a trace whose `messages`
  includes a `Message(role="system", ...)` entry; requesting a mix of a conversational metric name
  (e.g. `conversation_completeness`, fake-registered to raise the real pydantic `ValidationError`
  a `Turn(role="system", ...)` would raise) and a non-conversational metric name (e.g. `bias`,
  fake-registered to succeed) in the same `evaluate()` call; asserts the conversational metric's
  `MetricResult` is isolated-failed (`score is None`, `passed is False`, populated `error`) while
  `bias`'s result completes normally in the same `EvaluationResult` — spec.md Edge Cases, exercises
  FR-003's "no filtering/remapping" guarantee end-to-end
- [X] T046a Update `tests/unit/evaluation/test_evaluation_orchestrator.py` — touches the same file
  as T046, sequential, applied after it: add
  `test_empty_or_single_turn_messages_isolates_only_multi_turn_conversational_metrics` — a trace
  whose `messages` is `[]` (and a variant with exactly one turn); requesting a mix of the five
  multi-turn-dependent conversational metric names (`conversation_completeness`, `turn_relevancy`,
  `knowledge_retention`, `role_adherence`, `conversational_g_eval`, fake-registered to raise the
  real `MissingTestCaseParamsError` that `ConversationalTestCase.turns == []`/single-turn triggers
  inside each native metric's own `check_conversational_test_case_params`) and a non-conversational
  metric name (e.g. `bias`, fake-registered to succeed) in the same `evaluate()` call; asserts each
  multi-turn conversational metric's `MetricResult` is isolated-failed (`score is None`,
  `passed is False`, populated `error`) while `bias`'s result completes normally in the same
  `EvaluationResult` — spec.md Edge Cases (empty/single-turn `messages` bullet), exercises the same
  generic isolated-failure path as T046 but for the "no `messages`/single turn" case rather than the
  "invalid role" case
- [X] T047 Run the full quickstart.md validation suite — `uv run pytest tests/unit/evaluation -v`
  and `uv run pytest --cov=deepeval_platform --cov-report=term-missing --cov-fail-under=80` —
  confirm every spec.md acceptance scenario and edge case in quickstart.md's mapping table passes
  (including all pre-existing M3.1/M3.2 isolation/duplicate/timeout tests, unaffected by this
  milestone) and overall coverage remains ≥ 80%; fix any gap found

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: N/A — nothing to do before Phase 2
- **Foundational (Phase 2)**: BLOCKS all user stories — `ConversationalMetricBase` (T001–T002)
  blocks US1/US3/US4's conversational wrappers; the `MetricFactory.create()` generalization
  (T003–T004) blocks US3's `role_adherence` and all of US4's opt-in wrappers; `ConfigManager`'s list
  branch (T005–T006) blocks `BotMetricConfigResolver`'s `prompt_instructions` reads; the resolver
  itself (T007–T008) and its `EvaluationOrchestrator` wiring (T009–T010) block US3's
  `chatbot_role`-sourcing and all of US4's opt-in activation
- **User Story 1 (Phase 3)**: Depends only on Phase 2 (T002, T004) — independently implementable
  and testable first (MVP)
- **User Story 2 (Phase 4)**: Depends only on Phase 2 (T004) — no dependency on US1's new wrapper
  code; shares edit targets `native/__init__.py` (T015 → T023) and
  `test_conversation_strategy.py`/`conversation_strategy.py` growth path with US1/US3, purely
  sequential file edits, not a behavioral dependency
- **User Story 3 (Phase 5)**: Depends on Phase 2 (T002, T004, T008, T010 for `chatbot_role`
  forwarding) and, for the `ConversationStrategy`/test file edits only, comes after US2's edits to
  the same files (T026 → T034, T020 → T029) — no dependency on US1/US2's wrapper *behavior*
- **User Story 4 (Phase 6)**: Depends on Phase 2 (T002, T004, T006, T008) — no dependency on
  US1/US2/US3's wrapper behavior; shares `native/__init__.py`'s growth path (T033 → T044)
- **Polish (Phase 7)**: T046/T046a use fake-registered metric stubs (not the real US1/US2 wrapper
  classes), so they carry no genuine technical dependency on US1/US2 — the "depends on US1 and US2"
  ordering below is a single-developer sequencing convenience only (avoids touching
  `test_evaluation_orchestrator.py` before any real conversational/opt-in metric exists to motivate
  the test), and a parallel-team plan may run Phase 7's T046/T046a independently of US1/US2
  completion. T046 and T046a both edit `test_evaluation_orchestrator.py` and must be applied
  sequentially (T046 → T046a), not in parallel with each other. Full suite run (T047) genuinely
  depends on all four stories being complete, since it validates every acceptance scenario
  end-to-end.

### Within Each User Story

- Tests written and failing before implementation, per constitution Principle IV (NON-NEGOTIABLE):
  T011/T012 before T013–T015; T016–T020 before T021–T026; T027–T030 before T031–T034; T035–T039
  before T040–T045
- Wrapper implementation before the `native/__init__.py` import that triggers self-registration
  (T013/T014 before T015; T021/T022 before T023; T031/T032 before T033; T040–T043 before T044)
- Strategy `get_metrics()` changes make their paired test pass immediately (T024→T018, T025→T019,
  T026→T020, T034→T029)

### Parallel Opportunities

- T001, T003, T005, T007, T009 (five distinct test files in Phase 2) in parallel — but their
  paired implementation tasks (T002, T004, T006, T008, T010) have real inter-dependencies (T008
  needs T006; T010 needs T008 and T004), so implement in numeric order despite the tests being
  parallelizable
- T011 and T012 (US1, distinct test files) in parallel
- T016, T017, T018, T019, T020 (US2, distinct test files) in parallel
- T027, T028, T029, T030 (US3, distinct test files) in parallel
- T035, T036, T037, T038, T039 (US4, distinct test files) in parallel
- Once Phase 2 is complete, US1, US2, US3, and US4 could in principle be staffed in parallel by
  different developers — in practice US3/US4 share sequential edit targets with US1/US2
  (`native/__init__.py`, `conversation_strategy.py`) so a single-developer run should follow
  priority order (P1 → P2 → P3 → P4) to avoid merge conflicts, exactly as US2/US3's
  `ConversationStrategy` growth already assumes

---

## Parallel Example: Foundational Phase

```bash
# Launch all five Foundational test files together:
Task: "Write tests/unit/evaluation/metrics/test_conversational_metric_base.py"
Task: "Update tests/unit/evaluation/metrics/test_metric_factory.py"
Task: "Update tests/unit/config/test_config_manager.py"
Task: "Write tests/unit/evaluation/test_bot_metric_config_resolver.py"
Task: "Update tests/unit/evaluation/test_evaluation_orchestrator.py"
```

## Parallel Example: User Story 2

```bash
# Launch all five User Story 2 test/update tasks together:
Task: "Write tests/unit/evaluation/metrics/native/test_bias_metric.py"
Task: "Write tests/unit/evaluation/metrics/native/test_toxicity_metric.py"
Task: "Update tests/unit/evaluation/test_rag_strategy.py"
Task: "Update tests/unit/evaluation/test_agent_strategy.py"
Task: "Update tests/unit/evaluation/test_conversation_strategy.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 2: Foundational (CRITICAL — blocks all stories)
2. Complete Phase 3: User Story 1
3. **STOP and VALIDATE**: `conversation_completeness`/`turn_relevancy` resolve end-to-end via
   `ConversationStrategy.get_metrics()` — the currently-broken path (100% of conversational-bot
   evaluations failing today) is fixed
4. Deploy/demo if ready

### Incremental Delivery

1. Foundational → foundation ready (`ConversationalMetricBase`, generalized factory, resolver,
   orchestrator wiring)
2. Add User Story 1 → test independently → deploy/demo (MVP — fixes the broken path)
3. Add User Story 2 → test independently → deploy/demo (`bias`/`toxicity` cross-cutting safety)
4. Add User Story 3 → test independently → deploy/demo (`knowledge_retention`/`role_adherence`)
5. Add User Story 4 → test independently → deploy/demo (opt-in `summarization`/`json_correctness`/
   `prompt_alignment`/`conversational_g_eval`)
6. Each story adds value without breaking previous stories — `ConversationStrategy.get_metrics()`
   grows 2 → 4 → 6 entries across US1 → US2 → US3, always additive

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Verify tests fail before implementing (TDD, Principle IV)
- `MetricFactory.register()`, `EvaluationContext`, and `EvaluationResult` are never touched by any
  task in this file (SC-006) — only `MetricFactory.create()`'s signature is generalized (T004)
- Avoid: vague tasks, same-file conflicts within a single phase, cross-story dependencies that
  break independent testability

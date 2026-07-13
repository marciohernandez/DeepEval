# Tasks: MetricFactory + EvaluationStrategy Integration

**Input**: Design documents from `/specs/004-metric-factory-eval-strategy/`

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
Structure — no new top-level project.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Package skeleton and config schema extensions needed before any module can be built.

- [X] T001 Create the `deepeval_platform/evaluation/metrics/` and
  `deepeval_platform/evaluation/metrics/native/` sub-packages (empty `__init__.py` in each,
  populated later by T029/T028) and the mirrored `tests/unit/evaluation/metrics/` and
  `tests/unit/evaluation/metrics/native/` test directories (with `__init__.py` in each)
- [X] T002 [P] Extend `config/bots.yaml`: add a `metrics:` map under `test_rag_bot` with
  `faithfulness: {threshold: 0.8}` (sibling of the existing `bot_type`/`platform`/`field_mapping`
  keys), per contracts/evaluation-api.md's Configuration surface
- [X] T003 [P] Extend `config/settings.yaml`: add a top-level `evaluation:` section with
  `metric_timeout_seconds: 30` (global default), `metric_timeout_overrides: {faithfulness: 60}`,
  and `llm_judge: {provider: openai, model: gpt-4o}`, per contracts/evaluation-api.md's
  Configuration surface

**Checkpoint**: Package skeleton and config schema exist — foundational modules can now be built.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Shared entities every user story depends on — errors, dataclasses, `MetricBase` ABC,
and the `MetricFactory` registry mechanism itself. No story-specific acceptance behavior is tested
here; each module gets its own contract test first (TDD).

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T004 [P] Write `tests/unit/evaluation/test_errors.py`: `ErrorDetail` construction; every
  `EvaluationOrchestratorError` subclass (`EmptyMetricListError`, `UnknownMetricError`,
  `DuplicateMetricRequestError`, `DuplicateMetricNameError`, `InvalidThresholdError`,
  `InvalidTimeoutError`, `ConfigResolutionError`) carries the identifying data its message needs
  (e.g. unknown/duplicate names, offending `(metric, value)` pairs); `sanitize_error()` redacts
  API-key-shaped tokens, `Bearer <token>` headers, and long opaque strings from `str(exc)`, and
  caps message length — per data-model.md's Exceptions table and research.md §6
- [X] T005 Implement `deepeval_platform/evaluation/errors.py`: `ErrorDetail` dataclass, the
  `EvaluationOrchestratorError` base and its six subclasses above, and `sanitize_error(exc) ->
  ErrorDetail` (`category = type(exc).__name__`, redacted/capped `message`) — makes T004 pass
- [X] T006 [P] Write `tests/unit/evaluation/test_evaluation_context.py`: `EvaluationContext` is a
  two-field dataclass (`trace: NormalizedTrace`, `thresholds: dict[str, float]`); construction
  from a `NormalizedTrace` (M2.2) + threshold map round-trips both fields unmodified, per FR-003
  and data-model.md
- [X] T007 Implement `deepeval_platform/evaluation/evaluation_context.py`: `EvaluationContext`
  dataclass exactly as specified in data-model.md (`trace`, `thresholds`) — makes T006 pass
- [X] T008 [P] Write `tests/unit/evaluation/test_evaluation_result.py`: `MetricResult` — `score is
  None` is always paired with `passed is False` and a populated `error: ErrorDetail`, never
  coerced to `0.0` (FR-006); `EvaluationResult.passed` is `True` iff every `MetricResult.passed`
  in `metrics` is `True` (AND aggregation, FR-007), covering both the all-pass and the
  any-fail case
- [X] T009 Implement `deepeval_platform/evaluation/evaluation_result.py`: `MetricResult` dataclass
  (`score`, `threshold`, `passed`, `error: ErrorDetail | None`) and `EvaluationResult` dataclass
  (`passed`, `metrics: dict[str, MetricResult]`) per data-model.md — makes T008 pass (depends on
  T005 for `ErrorDetail`)
- [X] T010 [P] Write `tests/unit/evaluation/metrics/test_metric_base.py`: a concrete test subclass
  of `MetricBase` setting `_native_metric_cls` to a mocked native `BaseMetric`; `measure(context)`
  builds an `LLMTestCase` from `context.trace` per the field mapping in research.md §7
  (`input`→`input`, `output`→`actual_output`, `expected_output`→`expected_output`,
  `context`→`retrieval_context`, `tools_called`→`deepeval.test_case.ToolCall(...)`), awaits
  `a_measure(test_case, _show_indicator=False)`, and returns a `MetricResult` wrapping
  `score`/`threshold`/`passed`/`reason`; `threshold`/`passed` properties proxy the native metric;
  an exception raised by the native metric's `a_measure` propagates out of `measure()` uncaught
  (isolation is the orchestrator's job per FR-011, not `MetricBase`'s)
- [X] T011 Implement `deepeval_platform/evaluation/metrics/metric_base.py`: `MetricBase` ABC with
  `_native_metric_cls: ClassVar[type[BaseMetric]]`, `__init__(threshold, deepeval_model)`
  constructing `self._native`, `threshold`/`passed` properties, and `async def measure(context)`
  per data-model.md and research.md §8 — makes T010 pass (depends on T007, T009)
- [X] T012 [P] Write `tests/unit/evaluation/metrics/test_metric_factory.py`: `create()` returns a
  new instance on every call for the same name (never caches/reuses, FR-008); `create()` with an
  unregistered name raises `UnknownMetricError` listing the received name and all supported names
  (FR-010); `register(name)` used a second time for an already-registered name raises
  `DuplicateMetricNameError` identifying the name and both classes (FR-009); `create()` never
  touches `ConfigManager` (FR-004)
- [X] T013 Implement `deepeval_platform/evaluation/metrics/metric_factory.py`: `MetricFactory`
  with `_registry: ClassVar[dict[str, type[MetricBase]]]`, `register(name)` classmethod decorator
  factory, and `create(name, *, threshold, deepeval_model)` classmethod per data-model.md — makes
  T012 pass (depends on T011, T005)

**Checkpoint**: Foundation ready — errors, dataclasses, `MetricBase`, and `MetricFactory` all
exist and are independently unit-tested. User story implementation can now begin.

---

## Phase 3: User Story 1 - Avaliar um trace com o conjunto de métricas do seu tipo de bot (Priority: P1) 🎯 MVP

**Goal**: Turn a `NormalizedTrace` + a list of canonical metric names into a concrete, aggregated
`EvaluationResult` — the end-to-end flow that gives `EvaluationStrategy.get_metrics()` (M2.1)
something real to produce.

**Independent Test**: Build an `EvaluationContext` from a sample `NormalizedTrace` and a fixed
metric-name list, run the evaluation flow, and verify the resulting `EvaluationResult` has a score
and status per requested metric — no dashboards, persistence, or trace collection involved.

### Tests for User Story 1 ⚠️

> Write these tests FIRST, ensure they FAIL before implementation.

- [X] T014 [P] [US1] Write `tests/unit/evaluation/metrics/native/test_answer_relevancy_metric.py`:
  `AnswerRelevancyMetricWrapper` is registered under `"answer_relevancy"` and its
  `_native_metric_cls` is DeepEval's `AnswerRelevancyMetric`
- [X] T015 [P] [US1] Write `tests/unit/evaluation/metrics/native/test_faithfulness_metric.py`:
  `FaithfulnessMetricWrapper` is registered under `"faithfulness"` and its `_native_metric_cls` is
  DeepEval's `FaithfulnessMetric`
- [X] T016 [P] [US1] Write
  `tests/unit/evaluation/metrics/native/test_contextual_precision_metric.py`:
  `ContextualPrecisionMetricWrapper` is registered under `"contextual_precision"` and its
  `_native_metric_cls` is DeepEval's `ContextualPrecisionMetric`
- [X] T017 [P] [US1] Write `tests/unit/evaluation/metrics/native/test_contextual_recall_metric.py`:
  `ContextualRecallMetricWrapper` is registered under `"contextual_recall"` and its
  `_native_metric_cls` is DeepEval's `ContextualRecallMetric`
- [X] T018 [P] [US1] Write
  `tests/unit/evaluation/metrics/native/test_contextual_relevancy_metric.py`:
  `ContextualRelevancyMetricWrapper` is registered under `"contextual_relevancy"` and its
  `_native_metric_cls` is DeepEval's `ContextualRelevancyMetric`
- [X] T019 [P] [US1] Write `tests/unit/evaluation/metrics/native/test_tool_correctness_metric.py`:
  `ToolCorrectnessMetricWrapper` is registered under `"tool_correctness"` and its
  `_native_metric_cls` is DeepEval's `ToolCorrectnessMetric`
- [X] T020 [US1] Write `tests/unit/evaluation/test_evaluation_orchestrator.py` (core flow +
  robustness edge cases, mocking `MetricFactory`/`MetricBase`/`ConfigManager`/`LLMProviderFactory`
  — no network access): `test_evaluate_returns_per_metric_results` (US1 AC1 — instantiate + run
  `answer_relevancy` + `faithfulness`, `EvaluationResult.metrics` has one entry per requested
  name); `test_metric_exception_isolated` (FR-011 — one metric's `measure()` raising doesn't
  block the others, failed metric gets `score=None`, `passed=False`, populated `error`);
  `test_metric_timeout_isolated_no_retry` (FR-015 — one metric's `measure()` exceeding its
  effective timeout is isolated the same way, and is never retried); `test_empty_metric_list_rejected`
  (FR-012 — `metric_names=[]` raises `EmptyMetricListError` before any `EvaluationContext` is
  built); `test_duplicate_metric_names_rejected` (FR-010 — repeated names in `metric_names` raise
  `DuplicateMetricRequestError` listing all duplicates); `test_invalid_threshold_aborts_before_any_measure`
  (FR-005 — a resolved threshold outside `0.0–1.0` or non-numeric raises `InvalidThresholdError`
  before any `measure()` call); `test_config_manager_failure_aborts` (FR-004 — `ConfigManager`
  raising while resolving bot config raises `ConfigResolutionError`, fail-closed)
- [X] T021 [US1] Write `tests/integration/test_evaluation_orchestrator_integration.py`: exercises
  `EvaluationOrchestrator.evaluate()` against a real `NormalizedTrace` and real metric wrapper
  classes with a mocked judge `DeepEvalBaseLLM` (no real network/API key required), asserting the
  full flow end-to-end — real `MetricFactory` registry, real threshold/timeout resolution via a
  test `ConfigManager` instance, real concurrent `asyncio.gather` execution, real AND aggregation

### Implementation for User Story 1

- [X] T022 [P] [US1] Implement
  `deepeval_platform/evaluation/metrics/native/answer_relevancy_metric.py`:
  `AnswerRelevancyMetricWrapper(MetricBase)` with `_native_metric_cls = AnswerRelevancyMetric`,
  `@MetricFactory.register("answer_relevancy")` — makes T014 pass (depends on T011, T013)
- [X] T023 [P] [US1] Implement `deepeval_platform/evaluation/metrics/native/faithfulness_metric.py`:
  `FaithfulnessMetricWrapper(MetricBase)` with `_native_metric_cls = FaithfulnessMetric`,
  `@MetricFactory.register("faithfulness")` — makes T015 pass (depends on T011, T013)
- [X] T024 [P] [US1] Implement
  `deepeval_platform/evaluation/metrics/native/contextual_precision_metric.py`:
  `ContextualPrecisionMetricWrapper(MetricBase)` with `_native_metric_cls =
  ContextualPrecisionMetric`, `@MetricFactory.register("contextual_precision")` — makes T016 pass
  (depends on T011, T013)
- [X] T025 [P] [US1] Implement
  `deepeval_platform/evaluation/metrics/native/contextual_recall_metric.py`:
  `ContextualRecallMetricWrapper(MetricBase)` with `_native_metric_cls = ContextualRecallMetric`,
  `@MetricFactory.register("contextual_recall")` — makes T017 pass (depends on T011, T013)
- [X] T026 [P] [US1] Implement
  `deepeval_platform/evaluation/metrics/native/contextual_relevancy_metric.py`:
  `ContextualRelevancyMetricWrapper(MetricBase)` with `_native_metric_cls =
  ContextualRelevancyMetric`, `@MetricFactory.register("contextual_relevancy")` — makes T018 pass
  (depends on T011, T013)
- [X] T027 [P] [US1] Implement
  `deepeval_platform/evaluation/metrics/native/tool_correctness_metric.py`:
  `ToolCorrectnessMetricWrapper(MetricBase)` with `_native_metric_cls = ToolCorrectnessMetric`,
  `@MetricFactory.register("tool_correctness")` — makes T019 pass (depends on T011, T013)
- [X] T028 [US1] Implement `deepeval_platform/evaluation/metrics/native/__init__.py`: import all
  six wrapper modules from T022–T027 so importing this package triggers their
  `@MetricFactory.register` self-registration (depends on T022, T023, T024, T025, T026, T027)
- [X] T029 [US1] Implement `deepeval_platform/evaluation/metrics/__init__.py`: import
  `deepeval_platform.evaluation.metrics.native` so importing this package triggers all six
  registrations (depends on T028)
- [X] T030 [US1] Implement `deepeval_platform/evaluation/evaluation_orchestrator.py`:
  `EvaluationOrchestrator.__init__(config=None)` (defaults to `ConfigManager.instance()`) and
  `async def evaluate(trace, bot_id, metric_names) -> EvaluationResult` implementing the full
  8-step flow from data-model.md — (1) reject empty list (FR-012); (2) validate all names
  registered + unique (FR-010); (3) resolve `{name: threshold}` via `ConfigManager` with native
  default fallback, validate `0.0–1.0` (FR-004/FR-005); (4) resolve global + per-metric timeout
  overrides, validate `> 0` (FR-015); (5) resolve the judge once via `LLMProviderFactory.create()`
  + `.as_deepeval_model()` (research.md §5); (6) build the one `EvaluationContext`; (7)
  `MetricFactory.create()` + concurrent `measure()` via `asyncio.gather` with per-metric
  `asyncio.wait_for` (FR-013/FR-014); (8) aggregate into `EvaluationResult`, isolating any
  per-metric exception/timeout without retry (FR-011/FR-015) — makes T020 and T021 pass (depends
  on T029, T013, T009, T007, T005). str→float conversion: `ConfigManager.get_optional(key,
  default="")` returns `""` for both "missing" and "configured empty" (identical by
  `ConfigManager.get()`'s own semantics) — treat `""` as not-configured (native default);
  non-empty values are parsed via `float(value)`, with `ValueError`/`TypeError` treated as an
  invalid explicit config value (fail-closed abort per FR-005/FR-015), per data-model.md's "str →
  float conversion" note.

**Checkpoint**: User Story 1 is fully functional and independently testable — a `NormalizedTrace`
+ metric-name list can be evaluated end-to-end into a scored, aggregated `EvaluationResult`.

---

## Phase 4: User Story 2 - Adicionar uma métrica nova sem tocar em código existente (Priority: P2)

**Goal**: Prove that a brand-new metric can register itself and become instantiable by name
through `MetricFactory` with zero changes to any existing file.

**Independent Test**: Define a new dummy metric with its self-registration declaration and
confirm it can be instantiated by name and used in an `EvaluationContext`, without touching
`MetricFactory` or any other pre-existing file.

### Tests for User Story 2 ⚠️

- [X] T031 [US2] Write `tests/unit/evaluation/metrics/test_metric_factory_extensibility.py`
  (verifies `MetricFactory`'s decorator-based self-registration — the first such pattern in this
  codebase; `StrategyFactory`'s extensibility test at
  `tests/unit/evaluation/test_strategy_factory_extensibility.py` covers a different mechanism, a
  hardcoded dict subclassed/merged in the factory's own source, not a decorator): a
  throwaway `_ThrowawayMetric(MetricBase)` test-local subclass self-registers via
  `@MetricFactory.register("custom_dummy_metric")` at test-module scope and is resolved correctly
  by `MetricFactory.create("custom_dummy_metric", ...)` (US2 AC1, SC-002 — zero production-file
  changes needed); the six real wrappers from US1 (`answer_relevancy`, `faithfulness`, etc.)
  remain resolvable and unaffected on the same real `MetricFactory._registry` (US2 AC2/AC3 are
  already covered by `test_metric_factory.py::test_create_unknown_name_raises` and
  `::test_register_duplicate_name_raises` from T012 — no new implementation needed here)

**Checkpoint**: User Story 2 is verified — adding a metric requires only a new subclass file; no
existing file (including `MetricFactory` itself) needs modification.

---

## Phase 5: User Story 3 - Aplicar threshold configurável por bot/métrica (Priority: P3)

**Goal**: A custom, per-bot/per-metric threshold configured in `config/bots.yaml` overrides the
DeepEval native default when resolved by `EvaluationOrchestrator`; absent configuration, the
native default applies.

**Independent Test**: Configure a custom threshold for one metric on one bot and confirm
`EvaluationResult` for that metric uses the configured value (not the native default); confirm
separately that, absent configuration, the native default is used.

### Tests for User Story 3 ⚠️

- [X] T032 [US3] Add to `tests/unit/evaluation/test_evaluation_orchestrator.py` (same file as
  T020, sequential — not parallel): `test_configured_threshold_applied` (US3 AC1 — with
  `config/bots.yaml`'s `test_rag_bot.metrics.faithfulness.threshold: 0.8` from T002 resolved via a
  mocked `ConfigManager`, the `faithfulness` `MetricResult.threshold` and pass/fail decision use
  `0.8`, not DeepEval's native default); `test_missing_config_uses_native_default` (US3 AC2 — a
  metric with no configured threshold for its bot resolves to that metric's DeepEval native
  default); `test_unknown_bot_id_uses_native_defaults` (edge case — a `bot_id` with zero
  `ConfigManager` entries is not an error; every metric falls back to its native default
  threshold/timeout, evaluation proceeds normally) — validates threshold-resolution behavior
  already implemented generically in T030's `evaluate()`; no new production code expected, but fix
  `evaluation_orchestrator.py` if any of these three cases fails

**Checkpoint**: All three user stories are independently functional — MVP (US1) plus
extensibility (US2) plus configurable thresholds (US3).

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Final verification across all stories.

- [X] T033 Run the full quickstart.md validation suite — `uv run pytest tests/unit/evaluation -v`,
  `uv run pytest tests/integration/test_evaluation_orchestrator_integration.py -v`, and `uv run
  pytest --cov=deepeval_platform --cov-report=term-missing --cov-fail-under=80` — confirm every
  spec.md acceptance scenario in quickstart.md's mapping table passes and overall coverage is
  ≥ 80% (SC-006); fix any gap found

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **Foundational (Phase 2)**: Depends on Setup (T001's package skeleton) — BLOCKS all user stories
- **User Story 1 (Phase 3)**: Depends on Foundational completion — no dependency on US2/US3
- **User Story 2 (Phase 4)**: Depends on Foundational completion; its test also exercises the six
  wrappers built in US1 (T022–T029), so run after Phase 3 in practice even though its own new code
  has no US1 dependency
- **User Story 3 (Phase 5)**: Depends on Foundational completion AND on T020/T030 from US1 (adds
  test cases to the orchestrator test file and validates the orchestrator built there) — not
  independently implementable before US1
- **Polish (Phase 6)**: Depends on all three user stories being complete

### Within Each User Story

- Tests written and failing before implementation (T014–T021 before T022–T030; T031 is
  self-contained; T032 validates already-built T030 behavior)
- Metric wrapper models (T022–T027) before the registration wiring that imports them (T028, T029)
- Registration wiring (T029) before the orchestrator that relies on a populated registry (T030)

### Parallel Opportunities

- T002 and T003 (different config files) in parallel
- T004, T006, T008, T010, T012 (five distinct test files, no cross-dependencies) in parallel
- T014–T019 (six distinct native-wrapper test files) in parallel
- T022–T027 (six distinct native-wrapper implementation files) in parallel, once T011/T013 exist

---

## Parallel Example: User Story 1

```bash
# Launch all six native-metric wrapper tests together:
Task: "Write tests/unit/evaluation/metrics/native/test_answer_relevancy_metric.py"
Task: "Write tests/unit/evaluation/metrics/native/test_faithfulness_metric.py"
Task: "Write tests/unit/evaluation/metrics/native/test_contextual_precision_metric.py"
Task: "Write tests/unit/evaluation/metrics/native/test_contextual_recall_metric.py"
Task: "Write tests/unit/evaluation/metrics/native/test_contextual_relevancy_metric.py"
Task: "Write tests/unit/evaluation/metrics/native/test_tool_correctness_metric.py"

# Then, once T011/T013 (MetricBase/MetricFactory) exist, launch all six wrapper implementations together:
Task: "Implement deepeval_platform/evaluation/metrics/native/answer_relevancy_metric.py"
Task: "Implement deepeval_platform/evaluation/metrics/native/faithfulness_metric.py"
Task: "Implement deepeval_platform/evaluation/metrics/native/contextual_precision_metric.py"
Task: "Implement deepeval_platform/evaluation/metrics/native/contextual_recall_metric.py"
Task: "Implement deepeval_platform/evaluation/metrics/native/contextual_relevancy_metric.py"
Task: "Implement deepeval_platform/evaluation/metrics/native/tool_correctness_metric.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (CRITICAL — blocks all stories)
3. Complete Phase 3: User Story 1
4. **STOP and VALIDATE**: run `uv run pytest tests/unit/evaluation tests/integration/test_evaluation_orchestrator_integration.py -v`
5. This is the MVP — `EvaluationStrategy.get_metrics()` now produces real scores

### Incremental Delivery

1. Setup + Foundational → foundation ready
2. Add User Story 1 → validate independently → MVP
3. Add User Story 2 → validate independently (extensibility proof, no runtime behavior change)
4. Add User Story 3 → validate independently (config-driven threshold override)
5. Phase 6: full quickstart.md + coverage gate validation

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Tests precede implementation in every phase per constitution Principle IV (NON-NEGOTIABLE)
- Verify each test file FAILS before writing the implementation that makes it pass
- Commit after each task or logical group
- Stop at any checkpoint to validate a story independently

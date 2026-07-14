# Tasks: HallucinationMetric + TaskCompletionMetric Integration

**Input**: Design documents from `/specs/005-rag-agentic-metrics/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, quickstart.md

**Tests**: Included and REQUIRED — constitution Principle IV (TDD, NON-NEGOTIABLE) and plan.md's
Testing section mandate tests before implementation, enforced by the existing
`pytest-cov --cov-fail-under=80` gate.

**Organization**: Tasks are grouped by user story (spec.md priorities P1/P2) to enable independent
implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2)
- File paths are exact and relative to the repository root

## Path Conventions

Single project (existing `deepeval_platform/` package + `tests/`), per plan.md's Project
Structure — no new top-level project, no new sub-package.

---

## Phase 1: Setup (Shared Infrastructure)

**N/A** — no new package skeleton, dependency, or config schema is needed. Both wrappers land in
the `deepeval_platform/evaluation/metrics/native/` sub-package already created in M3.1
(004-metric-factory-eval-strategy); the mirrored `tests/unit/evaluation/metrics/native/` directory
already exists too.

---

## Phase 2: Foundational (Blocking Prerequisites)

**N/A** — `MetricBase`, `MetricFactory`, `EvaluationContext`, `MetricResult`, `EvaluationResult`,
and `EvaluationOrchestrator` (all M3.1) are unmodified this milestone (plan.md Constitution Check,
SC-004). Both user stories below build directly on that existing foundation with no blocking
prerequisite work of their own.

---

## Phase 3: User Story 1 - Avaliar completude de tarefa em bots agênticos sem erro de métrica desconhecida (Priority: P1) 🎯 MVP

**Goal**: Register a `TaskCompletionMetricWrapper` under the canonical name `task_completion` so
`AgentStrategy.get_metrics()` (already declaring this name since M2.1) resolves successfully
end-to-end instead of failing every agentic-bot evaluation.

**Independent Test**: Build an `EvaluationContext` from a sample agentic `NormalizedTrace` and
`AgentStrategy().get_metrics()`, run the evaluation flow, and confirm the resulting
`EvaluationResult` contains a `task_completion` entry (score + pass/fail) alongside
`tool_correctness` — no change required to `AgentStrategy`, `MetricFactory`, or
`EvaluationOrchestrator`.

### Tests for User Story 1 ⚠️

> Write this test FIRST, ensure it FAILS before implementation.

- [X] T001 [P] [US1] Write `tests/unit/evaluation/metrics/native/test_task_completion_metric.py`
  (mirrors `test_tool_correctness_metric.py`'s pattern): `test_registered_under_canonical_name`
  (`MetricFactory._registry["task_completion"] is TaskCompletionMetricWrapper`) and
  `test_wraps_native_task_completion_metric`
  (`TaskCompletionMetricWrapper._native_metric_cls is TaskCompletionMetric` from `deepeval.metrics`)

### Implementation for User Story 1

- [X] T002 [US1] Implement
  `deepeval_platform/evaluation/metrics/native/task_completion_metric.py`:
  `TaskCompletionMetricWrapper(MetricBase)` with `_native_metric_cls = TaskCompletionMetric`
  (`deepeval.metrics`), `@MetricFactory.register("task_completion")` — no `_build_test_case`
  override needed (research.md §1: `TaskCompletionMetric._required_params` are `INPUT` and
  `ACTUAL_OUTPUT`, both already populated by the inherited `MetricBase._build_test_case`) — makes
  T001 pass
- [X] T003 [US1] Update `deepeval_platform/evaluation/metrics/native/__init__.py`: add
  `task_completion_metric,  # noqa: F401` to the existing alphabetically-ordered import tuple so
  importing this package triggers `TaskCompletionMetricWrapper`'s self-registration (depends on
  T002)

**Checkpoint**: User Story 1 is fully functional and independently testable —
`MetricFactory.create("task_completion", ...)` resolves, and the existing (unchanged)
`tests/unit/evaluation/test_agent_strategy.py` continues to assert `AgentStrategy.get_metrics() ==
["tool_correctness", "task_completion"]`, now backed by a real registered wrapper end-to-end.

---

## Phase 4: User Story 2 - Detectar alucinação em respostas de bots RAG (Priority: P2)

**Goal**: Register a `HallucinationMetricWrapper` under the canonical name `hallucination`,
supplying DeepEval's native metric with its required `context` test-case field via a
wrapper-local `_build_test_case` override (FR-007), and add `hallucination` to
`RAGStrategy.get_metrics()` so it runs automatically on every RAG bot evaluation.

**Independent Test**: Build an `EvaluationContext` from a sample RAG `NormalizedTrace` and
`RAGStrategy().get_metrics()`, run the evaluation flow, and confirm the resulting
`EvaluationResult` contains a `hallucination` entry alongside the five existing RAG metric
entries — without the caller requesting `hallucination` explicitly.

### Tests for User Story 2 ⚠️

> Write these tests FIRST, ensure they FAIL before implementation.

- [X] T004 [P] [US2] Write `tests/unit/evaluation/metrics/native/test_hallucination_metric.py`:
  `test_registered_under_canonical_name`
  (`MetricFactory._registry["hallucination"] is HallucinationMetricWrapper`),
  `test_wraps_native_hallucination_metric`
  (`HallucinationMetricWrapper._native_metric_cls is HallucinationMetric` from
  `deepeval.metrics`), and `test_build_test_case_populates_context_field` (FR-007 — given a
  `NormalizedTrace` with `context=["ctx1", "ctx2"]`,
  `HallucinationMetricWrapper._build_test_case(trace)` returns an `LLMTestCase` where both
  `context == ["ctx1", "ctx2"]` *and* `retrieval_context == ["ctx1", "ctx2"]`, and `input`/
  `actual_output`/`expected_output`/`tools_called` are mapped identically to
  `MetricBase._build_test_case`, per data-model.md)
- [X] T005 [P] [US2] Update `tests/unit/evaluation/test_rag_strategy.py`:
  `test_contains_expected_metric_names` now asserts the six-entry list `["answer_relevancy",
  "faithfulness", "contextual_precision", "contextual_recall", "contextual_relevancy",
  "hallucination"]` — same assertion, extended by one entry (Edge Cases, spec.md: the five
  existing entries are unchanged in content and order)

### Implementation for User Story 2

- [X] T006 [US2] Implement
  `deepeval_platform/evaluation/metrics/native/hallucination_metric.py`:
  `HallucinationMetricWrapper(MetricBase)` with `_native_metric_cls = HallucinationMetric`
  (`deepeval.metrics`) and a `@staticmethod _build_test_case(trace: NormalizedTrace) ->
  LLMTestCase` override reproducing `MetricBase._build_test_case`'s exact field mapping plus
  `context=trace.context` (research.md §2 — keep `retrieval_context=trace.context` too, do not
  drop it), `@MetricFactory.register("hallucination")` — makes T004 pass. Does not modify
  `MetricBase` or any other registered wrapper (FR-007).
- [X] T007 [US2] Update `deepeval_platform/evaluation/metrics/native/__init__.py`: add
  `hallucination_metric,  # noqa: F401` to the existing alphabetically-ordered import tuple so
  importing this package triggers `HallucinationMetricWrapper`'s self-registration (depends on
  T006; touches the same file as T003 — apply both edits sequentially, either order, to avoid a
  merge conflict)
- [X] T008 [US2] Update `deepeval_platform/evaluation/strategies/rag_strategy.py`: append
  `"hallucination"` as the sixth entry to the list returned by `RAGStrategy.get_metrics()`, after
  the five existing entries — makes T005 pass (research.md §3: pure additive change, no other
  member of `RAGStrategy` changes)

**Checkpoint**: User Story 2 is fully functional and independently testable —
`MetricFactory.create("hallucination", ...)` resolves, and `RAGStrategy.get_metrics()` returns all
six RAG metric names, so `hallucination` now runs automatically on every RAG bot evaluation
alongside the five metrics already in production since M3.1.

---

## Phase 5: Polish & Cross-Cutting Concerns

**Purpose**: Final verification across both stories.

- [X] T009 Run the full quickstart.md validation suite — `uv run pytest tests/unit/evaluation -v`
  and `uv run pytest --cov=deepeval_platform --cov-report=term-missing --cov-fail-under=80` —
  confirm every spec.md acceptance scenario in quickstart.md's mapping table passes (including the
  pre-existing `tests/unit/evaluation/test_evaluation_orchestrator.py::test_metric_exception_isolated`
  covering per-metric failure isolation, FR-005/SC-003, with no new orchestrator test needed) and
  overall coverage remains ≥ 80%; fix any gap found

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: N/A — nothing to do before Phase 3
- **Foundational (Phase 2)**: N/A — nothing to do before Phase 3
- **User Story 1 (Phase 3)**: No dependency on US2 — independently implementable and testable
  first (MVP)
- **User Story 2 (Phase 4)**: No dependency on US1's new code (`TaskCompletionMetricWrapper`);
  only shares the edit target `native/__init__.py` with US1's T003 (T007 — sequential, not a
  behavioral dependency)
- **Polish (Phase 5)**: Depends on both user stories being complete

### Within Each User Story

- Tests written and failing before implementation (T001 before T002/T003; T004/T005 before
  T006–T008) per constitution Principle IV (NON-NEGOTIABLE)
- Wrapper implementation before the `__init__.py` import that triggers self-registration
  (T002 before T003; T006 before T007)
- `RAGStrategy` change (T008) makes T005 pass; independent of T006/T007's file targets

### Parallel Opportunities

- T001 and T004 (distinct test files, distinct stories) in parallel
- T004 and T005 (distinct test files, both US2) in parallel
- T003 and T007 touch the same file (`native/__init__.py`) — not parallel with each other, but
  either can be done before the other

---

## Parallel Example: Both Stories

```bash
# Tests can be written in parallel across both stories:
Task: "Write tests/unit/evaluation/metrics/native/test_task_completion_metric.py"
Task: "Write tests/unit/evaluation/metrics/native/test_hallucination_metric.py"
Task: "Update tests/unit/evaluation/test_rag_strategy.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 3: User Story 1 (T001–T003)
2. **STOP and VALIDATE**: `uv run pytest tests/unit/evaluation/metrics/native/test_task_completion_metric.py tests/unit/evaluation/test_agent_strategy.py -v`
3. This closes the currently-broken `task_completion` path for every agentic-bot evaluation — the
   MVP for this milestone (SC-001)

### Incremental Delivery

1. Add User Story 1 → validate independently → unblocks all agentic-bot evaluations (MVP)
2. Add User Story 2 → validate independently → RAG bots gain automatic hallucination detection
3. Phase 5: full quickstart.md + coverage gate validation

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Tests precede implementation in every phase per constitution Principle IV (NON-NEGOTIABLE)
- Verify each test file FAILS before writing the implementation that makes it pass
- Commit after each task or logical group
- Stop at the Phase 3 checkpoint to validate User Story 1 (MVP) independently before starting
  User Story 2

# Phase 0 Research: HallucinationMetric + TaskCompletionMetric Integration

Both items below were open technical questions left to this plan by the spec's own Assumptions/
FR-007. Each is resolved with a verified finding against the installed `deepeval` package (not
guesswork).

## 1. `TaskCompletionMetric` required fields and construction

- **Decision**: `TaskCompletionMetricWrapper` needs **no override** — it is the same minimal body
  as the six M3.1 wrappers (`_native_metric_cls = TaskCompletionMetric`, nothing else).
- **Rationale**: Verified directly against the installed package
  (`deepeval/metrics/task_completion/task_completion.py`):
  - `TaskCompletionMetric._required_params = [SingleTurnParams.INPUT, SingleTurnParams.ACTUAL_OUTPUT]`
    only — both already populated unconditionally by `MetricBase._build_test_case` from
    `trace.input` / `trace.output`.
  - `TaskCompletionMetric.__init__` accepts `threshold`, `task` (optional, defaults `None`),
    `model`, `include_reason`, `async_mode`, `strict_mode`, `verbose_mode` — fully compatible with
    `MetricBase.__init__`'s existing `self._native_metric_cls(threshold=threshold,
    model=deepeval_model, async_mode=True)` call; no new constructor argument is required (the
    spec's Assumptions section explicitly excludes wiring the optional `task` parameter as new
    user-facing config this milestone).
  - `_a_extract_task_and_outcome` branches on `isinstance(test_case._trace_dict, Dict)`. This
    project's `LLMTestCase` construction (`MetricBase._build_test_case`) never sets
    `_trace_dict`, so every call takes the documented fallback path
    (`extract_goal_and_outcome` prompt built from `test_case.input`, `test_case.actual_output`,
    `test_case.tools_called`) — exactly the fields the shared base already populates, including
    `tools_called` (needed for the agentic-bot scenario in User Story 1, though not in
    `_required_params`).
- **Alternatives considered**: Overriding `_build_test_case` to pass a `task` description —
  rejected per spec Assumptions (out of scope this milestone); the native metric already falls
  back to inferring the task from input/output when `task` is `None`.

## 2. `HallucinationMetric` required fields — the `context` vs `retrieval_context` gap

- **Decision**: `HallucinationMetricWrapper` overrides `_build_test_case` (as a `staticmethod` on
  the subclass, shadowing `MetricBase._build_test_case` for instances of this class only) to set
  **both** `context=trace.context` and `retrieval_context=trace.context` — the same source list,
  mapped to both `LLMTestCase` fields. `MetricBase` itself, and the other six registered wrappers,
  are untouched (FR-007).
- **Rationale**: Verified directly against the installed package
  (`deepeval/metrics/hallucination/hallucination.py`):
  - `HallucinationMetric._required_params = [SingleTurnParams.INPUT, SingleTurnParams.ACTUAL_OUTPUT, SingleTurnParams.CONTEXT]`
    — `CONTEXT`, not `RETRIEVAL_CONTEXT`. `MetricBase._build_test_case` (research.md §7 of
    004-metric-factory-eval-strategy) only ever populates `retrieval_context` from
    `trace.context`; `context` is left at its default (`None`), so `check_llm_test_case_params`
    would raise `MissingTestCaseParamsError` on every call without this override — matching the
    spec's own framing of this as a 100%-failure case, not an edge case.
  - `LLMTestCase` (pydantic model, `deepeval.test_case`) has `context: Optional[List[str]] = None`
    as a distinct field from `retrieval_context: Optional[List[str]] = None` — confirmed both
    exist independently, so setting one does not implicitly populate the other.
  - Retaining `retrieval_context=trace.context` alongside the new `context=trace.context`
    (instead of dropping `retrieval_context`) is deliberate: no other part of
    `HallucinationMetric` reads `retrieval_context`, but keeping it preserves the exact shape
    `MetricBase._build_test_case` would have produced, minimizing the override's diff to "add one
    field" rather than "replace the whole construction."
- **Alternatives considered**:
  - Modifying `MetricBase._build_test_case` itself to always populate `context` from
    `trace.context` for every wrapper — rejected per the spec's own clarification answer (FR-007):
    scoped explicitly to `HallucinationMetricWrapper` only, to avoid any behavior change for the
    six already-registered wrappers.
  - Adding a new `NormalizedTrace` field dedicated to `context` — rejected; `NormalizedTrace` is
    frozen this milestone (spec Assumptions), and the existing `trace.context` data is already
    sufficient, just wired to the wrong `LLMTestCase` attribute.

## 3. `RAGStrategy.get_metrics()` change — additive-only verification

- **Decision**: Append `"hallucination"` as a sixth list entry, after the five existing entries,
  with no other change to `RAGStrategy`.
- **Rationale**: `RAGStrategy.get_metrics()` (`deepeval_platform/evaluation/strategies/
  rag_strategy.py`) is a pure `list[str]` literal with no branching — appending one entry cannot
  affect the other five (Edge Cases, spec.md). `EvaluationOrchestrator`/`StrategyFactory` consume
  this list generically by iterating and calling `MetricFactory.create()` per name (verified in
  M3.1's own `evaluation_orchestrator.py`); no code path treats list length or position as
  meaningful, so no other module requires a change (FR-003/SC-004).
- **Alternatives considered**: Registering `HallucinationMetricWrapper` in `MetricFactory` without
  touching `RAGStrategy` — rejected per the spec's own clarification answer; the milestone
  explicitly requires `hallucination` to run automatically on every RAG bot, not merely be
  available on request.

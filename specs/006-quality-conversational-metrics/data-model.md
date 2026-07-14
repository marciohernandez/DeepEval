# Phase 1 Data Model: Quality/Safety + Conversational Metrics Integration (M3.3)

No changes to `NormalizedTrace`, `EvaluationContext`, or `EvaluationResult` (SC-006). This document
covers only the new classes and the one field newly *consumed* (not added) from existing entities.

## ConversationalMetricBase (new — `deepeval_platform/evaluation/metrics/conversational_metric_base.py`)

Sibling ABC to `MetricBase` (M3.1), for the five metrics that require a `ConversationalTestCase`
(research.md §R2, §R8).

| Member | Type | Notes |
|---|---|---|
| `_native_metric_cls` | `ClassVar[type[BaseConversationalMetric]]` | set by each concrete subclass |
| `__init__(threshold, deepeval_model)` | — | constructs `self._native = self._native_metric_cls(threshold=threshold, model=deepeval_model, async_mode=True)` |
| `threshold` | `property -> float` | `self._native.threshold` |
| `passed` | `property -> bool \| None` | `self._native.success` |
| `measure(context) -> MetricResult` | `async` | builds test case via `_build_test_case`, awaits `self._native.a_measure(test_case, _show_indicator=False)`, returns `MetricResult` — identical shape to `MetricBase.measure` |
| `_build_test_case(trace, chatbot_role=None)` | `staticmethod -> ConversationalTestCase` | `ConversationalTestCase(turns=[Turn(role=m.role, content=m.content) for m in trace.messages], chatbot_role=chatbot_role)` |

Validation rule: an invalid `Message.role` (anything other than `"user"`/`"assistant"`) raises a
pydantic `ValidationError` when `Turn(...)` is constructed — this propagates unmodified through
`measure()` up to `EvaluationOrchestrator._measure_one`'s existing generic exception handler
(research.md §R2), producing the standard isolated `MetricResult(score=None, passed=False,
error=...)`. No new validation code in this class.

## New MetricBase subclasses (LLMTestCase-based — FR-001)

All under `deepeval_platform/evaluation/metrics/native/`, self-registered via
`@MetricFactory.register(name)`, following the exact pattern of the six M3.1 / two M3.2 wrappers.
None override `_build_test_case` — all five operate on fields `MetricBase._build_test_case`
already populates (`input`, `actual_output`, `expected_output`, `retrieval_context`,
`tools_called`).

| Class | File | Canonical name | Extra `__init__` kwarg | Forwarded to native as |
|---|---|---|---|---|
| `BiasMetricWrapper` | `bias_metric.py` | `bias` | none | — |
| `ToxicityMetricWrapper` | `toxicity_metric.py` | `toxicity` | none | — |
| `SummarizationMetricWrapper` | `summarization_metric.py` | `summarization` | none | — |
| `JsonCorrectnessMetricWrapper` | `json_correctness_metric.py` | `json_correctness` | `expected_schema: type[BaseModel]` | `JsonCorrectnessMetric(expected_schema=...)` |
| `PromptAlignmentMetricWrapper` | `prompt_alignment_metric.py` | `prompt_alignment` | `prompt_instructions: list[str]` | `PromptAlignmentMetric(prompt_instructions=...)` |

## New ConversationalMetricBase subclasses (FR-004)

All under `deepeval_platform/evaluation/metrics/native/`, self-registered the same way.

| Class | File | Canonical name | Extra `__init__` kwarg | Notes |
|---|---|---|---|---|
| `ConversationCompletenessMetricWrapper` | `conversation_completeness_metric.py` | `conversation_completeness` | none | closes FR-007 gap |
| `ConversationRelevancyMetricWrapper` | `conversation_relevancy_metric.py` | `turn_relevancy` | none | wraps native `TurnRelevancyMetric` (FR-005) |
| `KnowledgeRetentionMetricWrapper` | `knowledge_retention_metric.py` | `knowledge_retention` | none | |
| `RoleAdherenceMetricWrapper` | `role_adherence_metric.py` | `role_adherence` | `chatbot_role: str \| None = None` | passes through to `_build_test_case(trace, chatbot_role=chatbot_role)`; `None` yields the native `MissingTestCaseParamsError`, caught generically (FR-008, R2) |
| `ConversationalGEvalMetricWrapper` | `conversational_g_eval_metric.py` | `conversational_g_eval` | `criteria: str` | constructs `ConversationalGEval(name="Conversational Quality", criteria=criteria, threshold=..., model=..., async_mode=True)` — `name` is a fixed literal, not bot-configurable (spec scopes only `criteria` via `conversational_geval_criteria`) |

## BotMetricConfigResolver (new — `deepeval_platform/evaluation/bot_metric_config_resolver.py`)

Configuration-domain class (FR-015); reads only through `ConfigManager`; **no metric
instantiation or evaluation logic** (enforced by keeping this class metric-name-string-only, never
importing `MetricFactory` or any native/wrapper class).

| Method | Signature | Responsibility |
|---|---|---|
| `resolve_metric_names` | `(self, bot_id: str, strategy_metrics: list[str]) -> list[str]` | Returns `strategy_metrics` plus, in a fixed append order (`summarization`, `json_correctness`, `prompt_alignment`, `conversational_g_eval`), each opt-in name whose required config key(s) are present for `bot_id` (FR-009/FR-011/FR-012). Never removes or reorders `strategy_metrics`. |
| `resolve_options` | `(self, bot_id: str, metric_names: list[str]) -> dict[str, dict[str, object]]` | For each name in `metric_names` that needs extra constructor kwargs, resolves and returns them; every other name maps to `{}` (research.md §R3). |

Per-metric option resolution (all via `ConfigManager.get_optional` / the new indexed-list reads,
research.md §R4–R6):

| Metric | Config key(s) read | Resolution |
|---|---|---|
| `summarization` | `bots.<bot>.metrics.summarization.enabled` | presence check only (truthy per R6) — decides inclusion in `resolve_metric_names`, contributes no constructor option |
| `json_correctness` | `bots.<bot>.json_schema` | dotted path → `importlib.import_module` + `getattr` → `{"expected_schema": <class>}` (R5); absent ⇒ metric excluded entirely (FR-011) |
| `prompt_alignment` | `bots.<bot>.prompt_instructions.0`, `.1`, ... | indexed-probe reconstruction → `{"prompt_instructions": [...]}` (R4); empty/absent ⇒ metric excluded |
| `conversational_g_eval` | `bots.<bot>.conversational_geval_criteria` | `{"criteria": <string>}`; absent ⇒ metric excluded |
| `role_adherence` | `bots.<bot>.chatbot_role` | `{"chatbot_role": <string or None>}` — **always** included in the options dict for `role_adherence` when that name is present in `metric_names` (it is never excluded by absence, per FR-008/FR-010a — absence just means `chatbot_role=None` flows through to the native `MissingTestCaseParamsError` path) |
| all others | none | `{}` |

## Modified: `RAGStrategy`, `AgentStrategy` (FR-006)

`get_metrics()` gains two additive trailing entries: `"bias"`, `"toxicity"`. No existing entries
removed/reordered.

## Modified: `ConversationStrategy` (FR-007, FR-008)

`get_metrics()` grows from
`["conversation_completeness", "turn_relevancy"]` to
`["conversation_completeness", "turn_relevancy", "bias", "toxicity", "knowledge_retention", "role_adherence"]`
— the two existing (previously unregistered) names keep their position; four additive entries
appended.

## Modified: `MetricFactory.create()` (FR-016)

```python
@classmethod
def create(cls, name: str, *, threshold: float, deepeval_model: DeepEvalBaseLLM, **options: object) -> MetricBase:
```
`register()` and the `_registry` dict itself are unchanged (SC-006).

## Modified: `EvaluationOrchestrator` (FR-013)

`__init__` gains an optional injected `BotMetricConfigResolver` (default
`BotMetricConfigResolver()`), stored as `self._resolver`. `evaluate()` itself performs **no**
options resolution — `resolve_options` is resolved **per metric name, inside `_measure_one`'s
existing `try` block**, immediately before `MetricFactory.create`, so any exception it raises
(e.g. `ImportError`/`AttributeError` from a malformed `json_schema` dotted path, research.md §R5)
is caught by the same `except Exception` that already converts a metric-construction/measurement
failure into an isolated `MetricResult(score=None, passed=False, error=...)` for that name only —
identical to how `MetricFactory.create` failures are isolated today. `resolve_options` MUST NOT be
called eagerly across all `metric_names` in `evaluate()`'s pre-flight block (the block guarded by
`ConfigResolutionError`, alongside `_resolve_thresholds`/`_resolve_timeouts`/`_resolve_judge`) —
that block's contract is "any exception aborts the whole call," which is correct for
threshold/timeout/judge misconfiguration but would incorrectly fail every requested metric for one
bad opt-in key, contradicting spec.md's Edge Cases (a malformed opt-in key is an isolated
per-metric failure, not a whole-call abort) and FR-011/SC-005:
```python
try:
    options = self._resolver.resolve_options(bot_id, [name])[name]
    metric = MetricFactory.create(name, threshold=threshold, deepeval_model=judge, **options)
    return await asyncio.wait_for(metric.measure(context), timeout=timeout)
except asyncio.TimeoutError:
    ...  # unchanged
except Exception as exc:
    ...  # unchanged — now also catches resolve_options/MetricFactory.create failures
```
`evaluate()`'s public signature (`trace`, `bot_id`, `metric_names`) is unchanged (research.md §R3).
`EvaluationContext`, `EvaluationResult`, `MetricResult` are unchanged (SC-006).

## Modified: bot configuration schema (`config/bots.yaml`)

New optional per-bot keys (all read exclusively through `ConfigManager`, Principle V):

| Key | Type | Unlocks |
|---|---|---|
| `bots.<bot>.metrics.summarization.enabled` | bool | `summarization` opt-in |
| `bots.<bot>.json_schema` | string (dotted import path) | `json_correctness` opt-in |
| `bots.<bot>.prompt_instructions` | list of strings | `prompt_alignment` opt-in |
| `bots.<bot>.conversational_geval_criteria` | string | `conversational_g_eval` opt-in |
| `bots.<bot>.chatbot_role` | string | `role_adherence` persona (always attempted; this key's absence does not exclude the metric — FR-010a) |

## Modified: `ConfigManager._flatten_yaml` (research.md §R4)

Adds one branch: `list` values are flattened element-by-element into indexed sub-keys
(`{flat_key}.0`, `{flat_key}.1`, ...) instead of being `str()`-stringified whole. `get`,
`get_optional`, `get_typed`, and every existing scalar/dict-nested key are unaffected.

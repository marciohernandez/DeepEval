# Phase 0 Research: Quality/Safety + Conversational Metrics Integration (M3.3)

## R1. Native DeepEval class inventory (verified against installed `deepeval==4.0.7`)

Decision: use these native classes as-is (Principle II — DeepEval-First); no reimplementation.

| Canonical name | Native class | Base | Constructor params beyond `threshold`/`model`/`async_mode` |
|---|---|---|---|
| `bias` | `BiasMetric` | `BaseMetric` | none |
| `toxicity` | `ToxicityMetric` | `BaseMetric` | none |
| `summarization` | `SummarizationMetric` | `BaseMetric` | none required (`n`, `assessment_questions` left at native defaults) |
| `json_correctness` | `JsonCorrectnessMetric` | `BaseMetric` | `expected_schema: BaseModel` (**required**, no default) |
| `prompt_alignment` | `PromptAlignmentMetric` | `BaseMetric` | `prompt_instructions: list[str]` (**required**, no default) |
| `conversational_g_eval` | `ConversationalGEval` | `BaseConversationalMetric` | `name: str` (**required**), `criteria: str` (used; `evaluation_steps` not exposed by this milestone per spec) |
| `knowledge_retention` | `KnowledgeRetentionMetric` | `BaseConversationalMetric` | none |
| `role_adherence` | `RoleAdherenceMetric` | `BaseConversationalMetric` | none on the metric itself — reads `ConversationalTestCase.chatbot_role`, raises `MissingTestCaseParamsError` when `None` (verified in `deepeval.metrics.utils.check_conversational_test_case_params`, called with `require_chatbot_role=True`) |
| `conversation_completeness` | `ConversationCompletenessMetric` | `BaseConversationalMetric` | none |
| `turn_relevancy` | `TurnRelevancyMetric` | `BaseConversationalMetric` | none (FR-005 — the only native class matching "ConversationRelevancyMetric" intent) |

All ten expose the same `score` / `threshold` / `success` / `.a_measure(test_case, _show_indicator=False)` surface `MetricBase` (M3.1) already depends on — no new native call pattern needed beyond the conversational test-case type.

**Alternatives considered**: none — Principle II leaves no choice once a native class satisfies the requirement, and all ten were confirmed importable from `deepeval.metrics`.

## R2. `ConversationalTestCase` / `Turn` shape (verified against installed package)

Decision: `ConversationalMetricBase._build_test_case` constructs:
```python
ConversationalTestCase(
    turns=[Turn(role=m.role, content=m.content) for m in trace.messages],
    chatbot_role=<resolved per FR-010a, or None>,
)
```
- `Turn.role` is `Literal["user", "assistant"]` (pydantic-enforced) and `Turn.content: str` (required). Constructing a `Turn` with any other role string raises a pydantic `ValidationError` **at construction time** — this is the mechanism that satisfies FR-003's "no filtering/remapping, isolated failure per conversational metric" requirement for free: no bespoke role-validation code is needed, the native model already refuses invalid roles, and the existing `EvaluationOrchestrator._measure_one` generic `except Exception` (already established M3.1) turns that into the standard isolated `MetricResult(score=None, passed=False, error=...)`.
- `ConversationalTestCase.turns == []` (empty `messages`) raises `MissingTestCaseParamsError` inside every native conversational metric's own `check_conversational_test_case_params` call — again, no bespoke "empty messages" branch is needed in this project's code; the isolation already flows through the same generic exception path.
- `chatbot_role: Optional[str]` is the only field this milestone needs beyond `turns`; `scenario`, `expected_outcome`, `context`, etc. are not required by any of the five conversational metrics in scope (verified: none of `ConversationCompletenessMetric`, `TurnRelevancyMetric`, `KnowledgeRetentionMetric`, `RoleAdherenceMetric`, `ConversationalGEval` declare `_required_test_case_params` beyond `CONTENT`/`ROLE`, plus `CHATBOT_ROLE` for `RoleAdherenceMetric` only).

**Alternatives considered**: pre-validating roles in Python before constructing `Turn` and raising a custom error — rejected, it would duplicate validation DeepEval's own model already performs, violating Principle II's "used as-is" requirement and adding code with no behavioral difference from the isolated-failure path already in place.

## R3. Integration point: `EvaluationOrchestrator` currently has no strategy-aware caller

Finding: `EvaluationOrchestrator.evaluate(trace, bot_id, metric_names)` (M3.1) takes an explicit, caller-supplied `metric_names` list. Grepping the full `deepeval_platform/` tree confirms **no production code today calls `StrategyFactory.create(...).get_metrics()` and forwards the result into `orchestrator.evaluate()`** — `main.py` is still the scaffold stub, and every existing call site is a test that passes a hand-written `metric_names` list and asserts exact keys/behavior on the returned `EvaluationResult.metrics` (duplicate detection, unknown-metric errors, timeout isolation, etc.).

Decision: keep `EvaluationOrchestrator.evaluate()`'s public signature (`trace`, `bot_id`, `metric_names`) **unchanged**. `BotMetricConfigResolver` (FR-015) exposes two independent, side-effect-free methods:
- `resolve_metric_names(bot_id, strategy_metrics: list[str]) -> list[str]` — merges the strategy's automatic list with whatever opt-in metrics (`summarization`, `json_correctness`, `prompt_alignment`, `conversational_g_eval`) the bot's config unlocks (FR-009/FR-011/FR-012). Callers assembling a metric list (future scheduler/pipeline code, or a test) call this instead of hand-writing the merge.
- `resolve_options(bot_id, metric_names: list[str]) -> dict[str, dict]` — for each name in `metric_names` that needs extra constructor kwargs (`json_correctness` → `expected_schema`, `prompt_alignment` → `prompt_instructions`, `conversational_g_eval` → `criteria` (the `name="Conversational Quality"` half of the constructor is a
  fixed literal inside `ConversationalGEvalMetricWrapper.__init__`, not resolver output —
  `resolve_options` never returns a `name` key), `role_adherence` → `chatbot_role`), returns those kwargs; every other metric maps to `{}`.

`evaluate()` itself performs no options resolution up front. `BotMetricConfigResolver` is injected into the orchestrator's `__init__` (constructor param, default `BotMetricConfigResolver()`) as `self._resolver`, and `resolve_options(bot_id, [name])` is called once **per metric name, inside `_measure_one`'s existing `try` block**, immediately before `MetricFactory.create`. This is purely additive: every existing M3.1/M3.2 orchestrator test that never configures the four opt-in keys gets `resolve_options(bot_id, [name])[name] == {}` for every name, so `MetricFactory.create(name, threshold=..., deepeval_model=...)` is called exactly as before, byte-for-byte compatible. Scoping the call inside the per-metric `try` block (rather than once for the whole `metric_names` list in a pre-flight step) is what makes a malformed opt-in key an isolated single-metric failure instead of aborting the whole `evaluate()` call — see spec.md's Edge Cases and data-model.md §"Modified: EvaluationOrchestrator".

**Rationale**: the spec's Key Entities section says the orchestrator "obtains the bot's merged metric list and constructor options from `BotMetricConfigResolver`" — read together with FR-013's "MAY extend `EvaluationOrchestrator`" (not "MUST change its signature") and SC-006/SC-007's demand that `EvaluationContext`/`EvaluationResult` and the factory/orchestrator's *existing* integration points stay untouched, splitting resolution into "get the list" (used by whoever assembles `metric_names`) vs. "get the options" (consumed internally by the orchestrator once it already has a `metric_names` list) is the only reading that doesn't silently change what today's orchestrator tests observe. Auto-merging strategy metrics inside `evaluate()` itself would make every existing test that passes a deliberately short `metric_names` list (e.g., testing `EmptyMetricListError`, duplicate detection, a single metric in isolation) start receiving extra unrequested metric results — a breaking change the spec does not ask for and Gate "Pattern compliance" (constitution Quality Gate 4: "no changes to existing... implementations" behavior) would flag.

**Alternatives considered**:
- Auto-merge inside `evaluate()` by having it call `StrategyFactory` itself — rejected: couples the orchestrator to bot-type resolution it has never needed, and breaks the "explicit metric_names, exact keys back" contract every existing orchestrator test relies on.
- Change `evaluate()`'s signature to accept a `strategy` param instead of `metric_names` — rejected: violates SC-006 ("only backward-compatible integration changes... `MetricFactory.create()` and `EvaluationOrchestrator`") since existing tests call `evaluate(trace=..., bot_id=..., metric_names=...)` by keyword.

## R4. `ConfigManager` cannot represent a YAML list today — `prompt_instructions` needs one

Finding: `ConfigManager._flatten_yaml` (`deepeval_platform/config/config_manager.py:79-91`) recurses into `dict` values only; any other value (including a `list`) hits the `else` branch and is stored via `str(v)` — i.e., a YAML list like `prompt_instructions: ["Be concise", "Use bullet points"]` would currently be flattened to the single flat key `bots.<bot>.metrics.prompt_instructions` holding the **Python `repr` string** `"['Be concise', 'Use bullet points']"`, not a real list. `PromptAlignmentMetric.prompt_instructions` requires an actual `list[str]`.

Decision: extend `ConfigManager._flatten_yaml` with one additional branch — when `v` is a `list`, flatten each element under an indexed sub-key (`{flat_key}.0`, `{flat_key}.1`, ...) using the same recursion (so a list of scalars becomes N flat string entries), instead of stringifying the whole list. `BotMetricConfigResolver` reconstructs the list by probing `config.get_optional(f"{key}.{i}", default=None)` for `i = 0, 1, 2, ...` until a `None` is hit. No new public method is added to `ConfigManager`; `get`/`get_optional`/`get_typed` and every existing flat-scalar key (thresholds, timeouts, provider/model strings) are completely unaffected, since none of them are list-valued today. Verified this is additive-only: the existing `ConfigManager` test suite (`tests/unit/config/test_config_manager.py`) exercises only scalar YAML/`.env` values, so it exercises the unchanged `dict`/else branches and is unaffected by the new `list` branch.

**Alternatives considered**:
- Have `BotMetricConfigResolver` read `bots.yaml` directly with `yaml.safe_load` — rejected outright: Principle V is explicit that "`ConfigManager` (Singleton) MUST be the sole point of configuration reading in the system. No other module may read `.env` or YAML files directly."
- Add a `ConfigManager.get_raw_section(key) -> Any` method returning an unflattened nested value from a retained raw-YAML tree — rejected in favor of the indexed-flattening approach: it would require `ConfigManager` to keep two parallel representations (flat store + raw tree) for a need (`list[str]`) that arises exactly once in the whole codebase so far, whereas indexed flattening reuses the exact mechanism (`_store` of flat strings, `get_optional`) every other config value already goes through, keeping `ConfigManager`'s contract uniform.
- Store list values as a single delimited string (e.g., comma-joined) — rejected: fragile for instruction strings that may themselves contain commas, and would need custom escaping the indexed-key approach avoids entirely.

## R5. `json_schema` resolution — dotted import path → live `BaseModel` class

Decision (already settled in spec Clarifications, confirmed against `importlib`): `BotMetricConfigResolver` resolves `bots.<bot>.json_schema` (a string like `"myapp.schemas.OrderConfirmation"`) via `importlib.import_module(module_path)` + `getattr(module, class_name)`, splitting on the last `.`. A missing module, missing attribute, or an attribute that isn't a `pydantic.BaseModel` subclass is surfaced as the same isolated per-metric failure already established (spec Edge Cases) — the resolver does not special-case the error type, it lets `ImportError`/`AttributeError`/a `TypeError` guard propagate up through `EvaluationOrchestrator._measure_one`'s existing generic `except Exception` handler (M3.1), unchanged.

**Alternatives considered**: a dedicated YAML-driven dynamic Pydantic model builder — rejected per spec Clarifications, which explicitly settled on the dotted-import-path approach to keep the schema as ordinary versioned, type-checked project code (no new file format, no dynamic model construction).

## R6. `bots.<bot>.metrics.summarization.enabled` truthiness

Finding: because of R4/current flattening, `summarization.enabled: true` (a YAML bool, not a list) already flattens correctly today via the unchanged `dict`-recursion path — it lands as the flat string key `bots.<bot>.metrics.summarization.enabled` with value `"True"` (Python `str(True)`). This matches the pattern `EvaluationOrchestrator._resolve_thresholds` already uses for numeric YAML values (`float(raw)`).

Decision: `BotMetricConfigResolver` reads it via `config.get_optional(key, default="")` and treats any of `{"true", "1", "yes"}` (case-insensitive) as enabled, matching the loose-coercion style already established for thresholds/timeouts elsewhere in this codebase (`float(raw)` with a try/except), rather than requiring an exact-case `"True"` match.

**Alternatives considered**: `ConfigManager.get_typed(key, bool)` — rejected; Python's `bool("False")` is `True` (truthy non-empty string), so `get_typed` would silently misinterpret `enabled: false` as enabled. A dedicated string-set comparison avoids that trap without touching `ConfigManager` itself.

## R7. `MetricFactory.create()` generalization (FR-016)

Decision:
```python
@classmethod
def create(
    cls, name: str, *, threshold: float, deepeval_model: DeepEvalBaseLLM, **options: object
) -> MetricBase:
    if name not in cls._registry:
        raise UnknownMetricError(name, supported=sorted(cls._registry))
    return cls._registry[name](threshold=threshold, deepeval_model=deepeval_model, **options)
```
Every existing wrapper's `__init__(self, threshold, deepeval_model)` (inherited unchanged from `MetricBase`/new `ConversationalMetricBase`) simply receives zero extra kwargs when `options` is empty — identical behavior to every M3.1/M3.2 call site. Only the four opt-in wrappers (`JsonCorrectnessMetricWrapper`, `PromptAlignmentMetricWrapper`, `ConversationalGEvalMetricWrapper`, and `RoleAdherenceMetricWrapper` for `chatbot_role`) override `__init__` to accept their one additional keyword-only param and forward it to their own `_native_metric_cls(...)` call.

**Alternatives considered**: an `if name == "json_correctness": ...` branch inside `create()` — explicitly rejected by FR-016 ("without branching on canonical metric names") and by constitution Quality Gate 4 (Pattern compliance: Factory Method must not become an if/else chain).

## R8. Two-base-class design for `LLMTestCase` vs. `ConversationalTestCase` metrics (FR-002)

Decision: introduce `ConversationalMetricBase` as a sibling ABC to `MetricBase` (not a subclass — the two test-case types share no common constructor shape worth abstracting over, and forcing an artificial common parent would violate Principle I's single-responsibility guidance for no reuse benefit). Its shape mirrors `MetricBase` exactly (`__init__(threshold, deepeval_model)`, `.threshold`, `.passed`, `async def measure(context) -> MetricResult`) so `EvaluationOrchestrator._measure_one` needs zero changes to call either kind of wrapper polymorphically — both expose the same `measure(context) -> MetricResult` coroutine signature, which is the only interface the orchestrator depends on today.

**Alternatives considered**: making `ConversationalMetricBase` inherit `MetricBase` and override `_build_test_case` to return a `ConversationalTestCase` — rejected: `MetricBase._build_test_case` is a `@staticmethod` returning `LLMTestCase` used directly by `measure()`'s `self._native.a_measure(test_case, ...)`; a subclass changing the return type of an overridden static method while the parent's `measure()` body stays fixed is a Liskov violation waiting to happen the moment `MetricBase.measure()` is touched for an unrelated reason. Two independent, structurally-identical ABCs avoid that coupling entirely.

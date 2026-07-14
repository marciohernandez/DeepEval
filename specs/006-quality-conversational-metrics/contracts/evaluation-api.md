# Contract: Evaluation API Surface additions (M3.3)

Extends `specs/004-metric-factory-eval-strategy/contracts/evaluation-api.md` (still authoritative
for everything not listed here) and `specs/005-rag-agentic-metrics/plan.md` (no contract changes
in M3.2). This feature has no HTTP/CLI-facing surface of its own — same in-memory Python API
scope as M3.1/M3.2.

## `MetricFactory.create()` — generalized (FR-016, backward-compatible)

```python
from deepeval_platform.evaluation.metrics.metric_factory import MetricFactory

# Existing calls (M3.1–M3.2) remain valid, unchanged:
metric = MetricFactory.create("bias", threshold=0.5, deepeval_model=judge)

# New: generic keyword-only options forwarded verbatim to the wrapper's __init__,
# with zero branching on canonical metric names inside create() itself:
metric = MetricFactory.create(
    "json_correctness",
    threshold=0.5,
    deepeval_model=judge,
    expected_schema=OrderConfirmation,
)
metric = MetricFactory.create(
    "prompt_alignment", threshold=0.5, deepeval_model=judge,
    prompt_instructions=["Always respond in JSON", "Never mention competitors"],
)
metric = MetricFactory.create(
    "conversational_g_eval", threshold=0.5, deepeval_model=judge,
    criteria="Response stays on-topic and factually consistent across turns",
)
metric = MetricFactory.create(
    "role_adherence", threshold=0.5, deepeval_model=judge,
    chatbot_role="A polite banking support assistant",
)
```

- `create()` still NEVER returns `None`, still NEVER reads `ConfigManager` directly, still raises
  `UnknownMetricError` for an unregistered name — all unchanged from M3.1.
- Passing an option a wrapper's `__init__` doesn't declare raises the normal Python
  `TypeError: unexpected keyword argument` — `create()` does no validation of `options` itself,
  it is a pure pass-through (FR-016).
- `register()` and the `_registry` dict are unchanged (SC-006) — the ten new wrappers register the
  same way as every M3.1/M3.2 wrapper: `@MetricFactory.register("<name>")` on the class.

## `ConversationalMetricBase` — new sibling to `MetricBase` (FR-002)

```python
from deepeval_platform.evaluation.metrics.conversational_metric_base import ConversationalMetricBase

class ConversationCompletenessMetricWrapper(ConversationalMetricBase):
    _native_metric_cls = ConversationCompletenessMetric

MetricFactory.register("conversation_completeness")(ConversationCompletenessMetricWrapper)
```

- Same public shape as `MetricBase`: `__init__(threshold, deepeval_model)`, `.threshold`,
  `.passed`, `async def measure(context) -> MetricResult`. `EvaluationOrchestrator` calls either
  kind of wrapper identically — it does not know or care which base a given registered class uses.
- `measure()` MAY raise (e.g. `MissingTestCaseParamsError` for a missing `chatbot_role`, or a
  pydantic `ValidationError` for an invalid `Message.role`) — isolation is
  `EvaluationOrchestrator`'s job, unchanged from M3.1.

## `BotMetricConfigResolver` — new (FR-015)

```python
from deepeval_platform.evaluation.bot_metric_config_resolver import BotMetricConfigResolver
from deepeval_platform.evaluation.strategies.conversation_strategy import ConversationStrategy

resolver = BotMetricConfigResolver()  # reads through ConfigManager.instance() by default

metric_names = resolver.resolve_metric_names(
    bot_id="test_conversation_bot",
    strategy_metrics=ConversationStrategy().get_metrics(),
)
# -> strategy_metrics + any of [summarization, json_correctness, prompt_alignment,
#    conversational_g_eval] this bot's config unlocks, in that fixed append order.

options = resolver.resolve_options(bot_id="test_conversation_bot", metric_names=metric_names)
# -> dict[str, dict]; every name not needing extra kwargs maps to {}.
```

- Contains no metric instantiation or evaluation logic — never imports `MetricFactory` or any
  wrapper/native metric class (FR-015). A grep-level check: this module has zero
  `from deepeval_platform.evaluation.metrics` imports.
- A bot lacking a given opt-in key never appears in `resolve_metric_names`'s opt-in tail and never
  gets an entry that would raise a missing-argument error downstream (FR-011).
- `role_adherence` is a special case only insofar as it is **never excluded** by
  `resolve_metric_names` (it comes from the strategy list, not the opt-in tail); `resolve_options`
  always returns `{"chatbot_role": <str or None>}` for it whenever it's present in `metric_names`
  (FR-008, FR-010a).

## `EvaluationOrchestrator.evaluate()` — signature unchanged (FR-013)

```python
result: EvaluationResult = await orchestrator.evaluate(
    trace=normalized_trace,
    bot_id="test_conversation_bot",
    metric_names=[...],   # still explicit, still caller-supplied — unchanged from M3.1
)
```

- Internally, `evaluate()` performs no options resolution up front. A constructor-injected
  `BotMetricConfigResolver` (`self._resolver`, default `BotMetricConfigResolver()`) is called via
  `resolve_options(bot_id, [name])` once **per metric name, inside `_measure_one`'s existing `try`
  block**, immediately before `MetricFactory.create`, and the resolved options are forwarded into
  it. Every existing M3.1/M3.2 test — which never configures any of the four opt-in keys or
  `chatbot_role` — observes `{}` for every name, so this is byte-for-byte compatible with every
  existing assertion on `EvaluationResult`. Resolving per-name inside the `try` block (rather than
  once for the whole `metric_names` list) is required so a malformed opt-in key isolates only its
  own metric's `MetricResult`, per spec.md's Edge Cases.
- All existing pre-condition checks (`EmptyMetricListError`, `UnknownMetricError`,
  `DuplicateMetricRequestError`, `InvalidThresholdError`, `InvalidTimeoutError`,
  `ConfigResolutionError`) and post-conditions (one `MetricResult` per requested name, isolated
  per-metric failure, `result.passed` = AND over all metrics) are unchanged.

## Configuration surface additions (`config/bots.yaml`, read only through `ConfigManager`)

> **Illustrative only.** The block below shows every new key on a single bot purely to document the
> surface; it is not the literal fixture layout. The authoritative distribution of these keys across
> `config/bots.yaml`'s actual bots (which bot gets which key, and why `test_conversation_bot` must
> keep `chatbot_role` absent) is task T045 in `tasks.md`.

```yaml
bots:
  test_conversation_bot:
    bot_type: conversation
    platform: flowise
    chatbot_role: "A polite banking support assistant"        # NEW — role_adherence (FR-010a)
    conversational_geval_criteria: "Stays on-topic across turns"  # NEW — opt-in (FR-010)
    metrics:
      summarization:
        enabled: true                                         # NEW — opt-in (FR-009)
    json_schema: "myapp.schemas.OrderConfirmation"              # NEW — opt-in (FR-010)
    prompt_instructions:                                        # NEW — opt-in (FR-010)
      - "Always respond in JSON"
      - "Never mention competitors"
    field_mapping:
      # ... unchanged ...
```

- All five keys are optional; a bot declaring none of them is entirely unaffected (SC-004) — no
  error, no attempted execution of the corresponding opt-in metric.
- `ConfigManager` remains the sole reader (Principle V); no other module parses `bots.yaml`.

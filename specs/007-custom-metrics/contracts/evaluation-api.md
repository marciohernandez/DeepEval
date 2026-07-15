# Contract: Evaluation API Surface additions (M3.4)

Extends `specs/004-metric-factory-eval-strategy/contracts/evaluation-api.md` and
`specs/006-quality-conversational-metrics/contracts/evaluation-api.md` (both still authoritative
for everything not listed here). This feature has no HTTP/CLI-facing surface of its own — same
in-memory Python API scope as M3.1-M3.3.

## `MetricFactory.create()` — no change, three more registered names use it

```python
from deepeval_platform.evaluation.metrics.metric_factory import MetricFactory

metric = MetricFactory.create(
    "g_eval", threshold=0.5, deepeval_model=judge,
    criteria="Response must maintain a formal tone and never promise a delivery date",
)
metric = MetricFactory.create(
    "dag", threshold=0.5, deepeval_model=judge,
    dag=my_bot_module.build_refund_flow_dag(),  # already-invoked DeepAcyclicGraph — see resolver contract below
)
metric = MetricFactory.create("ragas_answer_correctness", threshold=0.5, deepeval_model=judge)
metric = MetricFactory.create("ragas_context_recall", threshold=0.5, deepeval_model=judge)
```

- `create()` itself is unmodified — same generic `**options` pass-through M3.3 already
  generalized it to (FR-016 unchanged). No branching added for any of the four new names.
- `register()` and the `_registry` dict are unchanged (SC-005). `g_eval` and `dag` each register
  a distinct class; `ragas_answer_correctness`/`ragas_context_recall` both register
  `RagasMetricWrapper`, applied twice with a different fixed `ragas_metric_name` baked in per
  registration (e.g. via a small `functools.partial`-style binding at import time) — from
  `MetricFactory`'s point of view these are simply two more ordinary registered subclasses.
- Passing `dag=` to `"g_eval"` (or `criteria=` to `"dag"`) raises the normal Python
  `TypeError: unexpected keyword argument` — unchanged pass-through behavior.

## `GEvalMetricWrapper` / `DAGMetricWrapper` — new `MetricBase` subclasses (FR-001, FR-004)

```python
from deepeval_platform.evaluation.metrics.native.g_eval_metric import GEvalMetricWrapper
from deepeval_platform.evaluation.metrics.native.dag_metric import DAGMetricWrapper

class GEvalMetricWrapper(MetricBase):
    _native_metric_cls = GEval
    def __init__(self, threshold, deepeval_model, criteria):
        self._native = GEval(
            name="Custom Criteria", criteria=criteria,
            evaluation_params=[SingleTurnParams.INPUT, SingleTurnParams.ACTUAL_OUTPUT],
            threshold=threshold, model=deepeval_model, async_mode=True,
        )

class DAGMetricWrapper(MetricBase):
    _native_metric_cls = DAGMetric
    def __init__(self, threshold, deepeval_model, dag):
        self._native = DAGMetric(
            name="Decision Graph", dag=dag, threshold=threshold, model=deepeval_model, async_mode=True,
        )
```

- Both follow the exact `MetricBase` extension pattern `JsonCorrectnessMetricWrapper`/
  `ConversationalGEvalMetricWrapper` already established (M3.3) — custom `__init__`, no
  `_build_test_case` override, no `MetricFactory`/`MetricBase` change.
- `measure()` MAY raise (e.g. a malformed `dag` object failing `DeepAcyclicGraph`'s own
  validation, or a `GEval` prompt/judge failure) — isolation is `EvaluationOrchestrator`'s job,
  unchanged from M3.1.

## `RagasMetricWrapper` — new `MetricBase` subclass, `measure()` overridden (FR-007, research.md §R3/§R4)

```python
from deepeval_platform.evaluation.metrics.native.ragas_metric import RagasMetricWrapper

metric = RagasMetricWrapper(threshold=0.5, deepeval_model=judge, ragas_metric_name="answer_correctness")
result: MetricResult = await metric.measure(context)
```

- Same public shape as `MetricBase`: `.threshold`, `.passed`, `async def measure(context) ->
  MetricResult`. `EvaluationOrchestrator` calls it identically to every native-delegating wrapper —
  it does not know or care that this one talks to Ragas instead of `a_measure()`.
- Internally builds a `ragas.dataset_schema.SingleTurnSample` from `context.trace` (mapping table
  in data-model.md), scores it via `await self._ragas_metric.single_turn_ascore(sample)`, and maps
  the resulting `float` into `MetricResult` — no native DeepEval `BaseMetric` involved.
- `measure()` MAY raise for any Ragas-side failure (misconfigured judge/embeddings, Ragas internal
  error, timeout) — isolation is `EvaluationOrchestrator`'s job, unchanged from M3.1 (research.md
  §R5 — this covers the "ragas package/config missing" edge case too, since `ragas` is now an
  ordinary non-optional dependency; any import-time failure would surface at process startup, not
  per-metric, and is out of this feature's isolation contract).

## `RagasLLMAdapter` — new (FR-009)

```python
from deepeval_platform.llm.ragas_adapter import RagasLLMAdapter

adapter = RagasLLMAdapter(deepeval_model=judge)  # judge: DeepEvalBaseLLM, same instance EvaluationOrchestrator._resolve_judge() already produces
```

- Implements `ragas.llms.base.BaseRagasLLM`'s abstract surface (`agenerate_text`, `generate_text`,
  `is_finished`) by delegating to the wrapped `DeepEvalBaseLLM`'s `a_generate`/`generate` — no
  LangChain (`LangchainLLMWrapper`) involved (Principle III).
- Does not modify `LLMProviderFactory`, `LLMProviderBase`, or any concrete provider class (FR-009).
- Scoped narrowly: only the calls `AnswerCorrectness`/`ContextRecall` actually make are supported
  — not a general-purpose Ragas LLM compatibility layer (spec Assumptions).

## `BotMetricConfigResolver` — three new branches (FR-002, FR-005, FR-008, FR-012)

```python
from deepeval_platform.evaluation.bot_metric_config_resolver import BotMetricConfigResolver
from deepeval_platform.evaluation.strategies.rag_strategy import RAGStrategy

resolver = BotMetricConfigResolver()

metric_names = resolver.resolve_metric_names(
    bot_id="test_rag_bot", strategy_metrics=RAGStrategy().get_metrics(),
)
# -> strategy_metrics + any of [summarization, json_correctness, prompt_alignment,
#    conversational_g_eval, g_eval, dag, ragas_answer_correctness, ragas_context_recall]
#    this bot's config unlocks, in that fixed append order.

options = resolver.resolve_options(bot_id="test_rag_bot", metric_names=metric_names)
# -> dict[str, dict]; "dag" maps to {"dag": <already-invoked DeepAcyclicGraph>};
#    "g_eval" maps to {"criteria": <string>}; both ragas_* map to {} (selector is fixed
#    per canonical name at MetricFactory registration, not resolved per-bot).
```

- Still contains no metric instantiation or evaluation logic — never imports `MetricFactory` or
  any wrapper/native metric class (FR-012, same grep-level invariant as M3.3).
- `dag_builder` resolution is the one method that **calls** the resolved attribute
  (`getattr(module, class_name)()`) rather than using it as-is — the only such case among every
  dotted-import-path config key this project has (`json_schema` remains as-is, unchanged). See
  research.md §R2 for why (FR-005's explicit clarification).
- A bot lacking a given opt-in key never appears in `resolve_metric_names`'s opt-in tail and never
  gets an entry that would raise a missing-argument error downstream (FR-003, FR-006, FR-008).
- `ragas_answer_correctness` and `ragas_context_recall` are independent opt-ins — a bot may enable
  either, both, or neither without affecting the other (spec Edge Cases).

## `EvaluationOrchestrator.evaluate()` — signature and internals unchanged (FR-011, SC-005)

```python
result: EvaluationResult = await orchestrator.evaluate(
    trace=normalized_trace,
    bot_id="test_rag_bot",
    metric_names=[...],   # still explicit, still caller-supplied — unchanged
)
```

- No change to `evaluate()`, `_measure_one`, or any pre-condition/post-condition check. The
  existing per-name `resolve_options(bot_id, [name])` call inside `_measure_one`'s `try` block
  (M3.3) already covers `g_eval`/`dag`/both Ragas names with zero orchestrator changes — this is
  exactly why FR-011/SC-005 can be satisfied without touching this class.
- A malformed `dag_builder` path (bad import, `AttributeError`, or the resolved callable raising)
  surfaces as an exception from `resolve_options`, caught by the same generic `except Exception` in
  `_measure_one` that already isolates every other opt-in-metric misconfiguration — producing
  `MetricResult(score=None, passed=False, error=...)` for `dag` alone (spec Edge Cases).

## Configuration surface additions (`config/bots.yaml`, read only through `ConfigManager`)

> **Illustrative only.** The block below shows every new key on a single bot purely to document the
> surface; the authoritative distribution of these keys across `config/bots.yaml`'s actual bots is
> a `tasks.md` task.

```yaml
bots:
  test_rag_bot:
    bot_type: rag
    platform: flowise
    geval_criteria: "Response must stay formal and never promise a delivery date"  # NEW — g_eval opt-in (FR-002)
    dag_builder: "myapp.dags.refund_flow.build_dag"                                # NEW — dag opt-in (FR-005)
    metrics:
      ragas_answer_correctness:
        enabled: true                                                              # NEW — opt-in (FR-008)
      ragas_context_recall:
        enabled: true                                                              # NEW — opt-in (FR-008)
    field_mapping:
      # ... unchanged ...
```

- All four keys are optional; a bot declaring none of them is entirely unaffected (SC-001/SC-002/
  SC-003) — no error, no attempted execution of the corresponding opt-in metric.
- `ConfigManager` remains the sole reader (Principle V); no other module parses `bots.yaml`.
- `dag_builder`'s referenced callable (e.g. `myapp.dags.refund_flow.build_dag`) must be a
  versioned, type-checked, zero-argument Python function or class in the codebase — there is no
  YAML-only path to activate `dag` (SC-006).

# Contract: Evaluation API Surface (internal Python API — no external network interface)

This feature has no HTTP/CLI-facing surface of its own (M3.1 is a pure in-memory library layer
consumed by future orchestration code, e.g. a scheduler job or API endpoint in a later
milestone). The "contract" here is the Python API other modules and tests may depend on.

## `MetricFactory`

```python
from deepeval_platform.evaluation.metrics.metric_factory import MetricFactory
from deepeval_platform.evaluation.metrics import native  # noqa: F401 — triggers self-registration

metric = MetricFactory.create(
    "faithfulness",
    threshold=0.8,
    deepeval_model=judge.as_deepeval_model(),
)  # -> MetricBase instance, fresh every call

MetricFactory.create("nonexistent")
# -> UnknownMetricError: "Unknown metric 'nonexistent'. Supported: [...]"
```

- `create()` NEVER returns `None` and NEVER reads `ConfigManager`.
- Registering two subclasses under the same name raises `DuplicateMetricNameError` at import
  time (i.e. as soon as the second module is imported), not at `create()` time.

## `MetricBase`

```python
from deepeval_platform.evaluation.evaluation_context import EvaluationContext

result: MetricResult = await metric.measure(context)
metric.threshold  # float
metric.passed     # bool | None
```

- `measure()` is a coroutine; callers needing a blocking call use `asyncio.run(metric.measure(...))`
  directly — `MetricBase` itself provides no sync wrapper (the orchestrator is the intended caller).
- `measure()` MAY raise (e.g. `MissingTestCaseParamsError`, provider network errors, DeepEval
  internal errors) — isolation is the orchestrator's job, not `MetricBase`'s.

## `EvaluationOrchestrator` — the primary entry point for this feature

```python
from deepeval_platform.evaluation.evaluation_orchestrator import EvaluationOrchestrator

orchestrator = EvaluationOrchestrator()  # uses ConfigManager.instance() by default
result: EvaluationResult = await orchestrator.evaluate(
    trace=normalized_trace,       # NormalizedTrace, M2.2
    bot_id="test_rag_bot",        # explicit, never inferred from the trace
    metric_names=["answer_relevancy", "faithfulness"],
)

result.passed                      # bool — AND over all requested metrics
result.metrics["faithfulness"].score      # float | None
result.metrics["faithfulness"].passed     # bool
result.metrics["faithfulness"].threshold  # float — configured or native default
result.metrics["faithfulness"].error      # ErrorDetail | None
```

**Pre-conditions enforced before any `measure()` call** (all raise `EvaluationOrchestratorError`
subclasses, abort the whole trace, produce zero `EvaluationResult`):

| Condition | Exception |
|---|---|
| `metric_names == []` | `EmptyMetricListError` |
| any name unregistered | `UnknownMetricError` |
| any name repeated | `DuplicateMetricRequestError` |
| any resolved threshold non-numeric or outside `0.0–1.0` | `InvalidThresholdError` |
| global timeout or any override non-numeric or `<= 0` | `InvalidTimeoutError` |
| `ConfigManager` itself raises while resolving bot config | `ConfigResolutionError` |

**Post-conditions**:
- `result.metrics` has exactly one key per entry in `metric_names`, always (SC-001).
- A per-metric exception or timeout never prevents the other metrics' entries from appearing
  (SC-003) and never raises out of `evaluate()` — it becomes a `MetricResult(score=None,
  passed=False, error=...)` entry instead.
- `result.passed` is `True` iff every `MetricResult.passed` is `True` (SC-004).
- No raw exception message, credential, or payload ever appears in any `ErrorDetail.message`
  (SC-008).

## Configuration surface (read-only from this feature's perspective; `ConfigManager` is the sole reader)

`config/bots.yaml` (per bot, new `metrics:` map — sibling of existing `bot_type`/`platform`/
`field_mapping` keys):

```yaml
bots:
  test_rag_bot:
    bot_type: rag
    platform: flowise
    metrics:
      faithfulness:
        threshold: 0.8
    field_mapping:
      # ... unchanged ...
```

`config/settings.yaml` (new `evaluation:` section):

```yaml
evaluation:
  metric_timeout_seconds: 30
  metric_timeout_overrides:
    faithfulness: 60
  llm_judge:
    provider: openai
    model: gpt-4o
```

Resolved dotted keys (via `ConfigManager`, unchanged flatten mechanism):
`bots.test_rag_bot.metrics.faithfulness.threshold`, `evaluation.metric_timeout_seconds`,
`evaluation.metric_timeout_overrides.faithfulness`, `evaluation.llm_judge.provider`,
`evaluation.llm_judge.model`.

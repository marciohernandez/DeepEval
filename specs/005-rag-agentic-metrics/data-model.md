# Phase 1 Data Model: HallucinationMetric + TaskCompletionMetric Integration

Both entities below are new concrete subclasses of `MetricBase` (M3.1,
`deepeval_platform/evaluation/metrics/metric_base.py`) — no existing type (`MetricBase`,
`MetricFactory`, `EvaluationContext`, `MetricResult`, `EvaluationResult`,
`EvaluationOrchestrator`, `NormalizedTrace`) is modified. `RAGStrategy` gains one list entry
(below); `AgentStrategy` is unchanged (it already declares `"task_completion"`).

## TaskCompletionMetricWrapper

`deepeval_platform/evaluation/metrics/native/task_completion_metric.py`

| Member | Value | Notes |
|---|---|---|
| `_native_metric_cls` | `TaskCompletionMetric` (`deepeval.metrics`) | Sole class attribute — identical shape to the six M3.1 wrappers (research.md §1). |
| `measure()`, `threshold`, `passed`, `_build_test_case()` | inherited, unmodified | No override needed — `TaskCompletionMetric._required_params` (`INPUT`, `ACTUAL_OUTPUT`) are already populated by the shared base. |

Registered via `@MetricFactory.register("task_completion")` at class definition — closes the name
already referenced by `AgentStrategy.get_metrics()` since M2.1 (FR-001, FR-004).

## HallucinationMetricWrapper

`deepeval_platform/evaluation/metrics/native/hallucination_metric.py`

| Member | Value | Notes |
|---|---|---|
| `_native_metric_cls` | `HallucinationMetric` (`deepeval.metrics`) | |
| `_build_test_case(trace: NormalizedTrace) -> LLMTestCase` | `@staticmethod`, **overridden** | Same as `MetricBase._build_test_case`, plus `context=trace.context` (research.md §2). `MetricBase._build_test_case` itself is not touched — this is a subclass-local override (FR-007). |
| `measure()`, `threshold`, `passed` | inherited, unmodified | `measure()` calls `self._build_test_case(context.trace)` via normal method resolution, so the override is picked up automatically with zero changes to `MetricBase.measure()`. |

Registered via `@MetricFactory.register("hallucination")` at class definition — adds a metric name
not referenced by any strategy before this milestone (FR-002).

**Field mapping (delta from research.md §7 of 004-metric-factory-eval-strategy)**:

| `NormalizedTrace` field | `LLMTestCase` field | Wrapper |
|---|---|---|
| `context` (list) | `retrieval_context` (list) | both (inherited from `MetricBase`) |
| `context` (list) | `context` (list) | `HallucinationMetricWrapper` only (new override) |

## RAGStrategy (modified)

`deepeval_platform/evaluation/strategies/rag_strategy.py`

`get_metrics()` return value changes from 5 to 6 entries:

```python
[
    "answer_relevancy",
    "faithfulness",
    "contextual_precision",
    "contextual_recall",
    "contextual_relevancy",
    "hallucination",   # NEW
]
```

No other member of `RAGStrategy` or `EvaluationStrategyBase` changes (research.md §3).

## AgentStrategy (unchanged, for reference)

`deepeval_platform/evaluation/strategies/agent_strategy.py` already returns
`["tool_correctness", "task_completion"]` since M2.1 — no code change here; this milestone makes
the second entry resolvable by registering `TaskCompletionMetricWrapper`.

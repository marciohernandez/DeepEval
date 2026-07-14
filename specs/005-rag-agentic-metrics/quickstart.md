# Quickstart: Validating HallucinationMetric + TaskCompletionMetric Integration

## Prerequisites

- `uv sync` already run (repo dependencies installed).
- A real judge-LLM API key in `.env` (`OPENAI_API_KEY` or `ANTHROPIC_API_KEY` or
  `OPENROUTER_API_KEY`) **only** for the optional manual end-to-end check below — all unit tests
  mock the native metric / `LLMProviderFactory` and require no network access or real credentials,
  matching the M3.1 convention (`tests/conftest.py::mock_env` / `mock_config`).

## Automated validation (primary path)

```bash
uv run pytest tests/unit/evaluation -v
uv run pytest --cov=deepeval_platform --cov-report=term-missing --cov-fail-under=80
```

Each acceptance scenario in `spec.md` maps to a specific automated test:

| Spec scenario | Test |
|---|---|
| US1 #1 — `AgentStrategy.get_metrics()` list evaluates end-to-end, `task_completion` entry present alongside `tool_correctness` | `tests/unit/evaluation/metrics/native/test_task_completion_metric.py::test_registered_under_canonical_name` + existing `tests/unit/evaluation/test_agent_strategy.py` (unchanged, already asserts the two-entry list) |
| US1 #2 — `MetricFactory.create("task_completion", ...)` returns a valid instance, zero changes elsewhere | `tests/unit/evaluation/metrics/native/test_task_completion_metric.py::test_wraps_native_task_completion_metric` |
| US2 #1 — `RAGStrategy.get_metrics()` includes `hallucination` alongside the five existing entries | `tests/unit/evaluation/test_rag_strategy.py::test_contains_expected_metric_names` (updated to assert the six-entry list) |
| US2 #2 — `MetricFactory.create("hallucination", ...)` returns a valid instance, zero changes elsewhere | `tests/unit/evaluation/metrics/native/test_hallucination_metric.py::test_wraps_native_hallucination_metric` |
| FR-007 — `HallucinationMetricWrapper` populates `context` from `trace.context`, `MetricBase._build_test_case` untouched | `tests/unit/evaluation/metrics/native/test_hallucination_metric.py::test_build_test_case_populates_context_field` |
| Edge: RAGStrategy's five pre-existing entries unchanged after adding `hallucination` | `tests/unit/evaluation/test_rag_strategy.py::test_contains_expected_metric_names` (same assertion — order and content both checked) |
| Edge: a `NormalizedTrace` missing fields either metric needs is isolated as a per-metric failure, not an unhandled exception | covered generically by the existing `tests/unit/evaluation/test_evaluation_orchestrator.py::test_metric_exception_isolated` (M3.1) — no new orchestrator test needed per FR-005 |

## Manual end-to-end check (optional, requires a real judge API key)

```python
import asyncio
from deepeval_platform.evaluation.evaluation_orchestrator import EvaluationOrchestrator
from deepeval_platform.normalization.models import NormalizedTrace

rag_trace = NormalizedTrace(
    input="What is the refund policy?",
    output="Refunds are available within 30 days of purchase, no questions asked, and we also ship you a free gift.",
    context=["Our refund policy allows returns within 30 days of purchase."],
    expected_output="Refunds within 30 days.",
)

orchestrator = EvaluationOrchestrator()
result = asyncio.run(
    orchestrator.evaluate(trace=rag_trace, bot_id="test_rag_bot", metric_names=["hallucination"])
)
print(result.metrics["hallucination"].score, result.metrics["hallucination"].passed)
```

**Expected outcome**: `result.metrics["hallucination"]` has a numeric `score` (low, since the
output invents an unsupported "free gift" claim) and `error is None` — confirming `context` was
supplied correctly and DeepEval's native metric ran without `MissingTestCaseParamsError`.

# Quickstart: Validating MetricFactory + EvaluationStrategy Integration

## Prerequisites

- `uv sync` already run (repo dependencies installed).
- A real judge-LLM API key in `.env` (`OPENAI_API_KEY` or `ANTHROPIC_API_KEY` or
  `OPENROUTER_API_KEY`) **only** for the end-to-end scenario (US1 acceptance test 1) — all unit
  tests mock `MetricBase`/`LLMProviderFactory` and require no network access or real credentials
  (`tests/conftest.py::mock_env` / `mock_config` already provide safe stubs).
- `config/bots.yaml` has a bot entry with a `metrics:` map (see contracts/evaluation-api.md) for
  the threshold-override scenario (US3).

## Automated validation (primary path)

```bash
uv run pytest tests/unit/evaluation -v
uv run pytest tests/integration/test_evaluation_orchestrator_integration.py -v
uv run pytest --cov=deepeval_platform --cov-report=term-missing --cov-fail-under=80
```

Each acceptance scenario in `spec.md` maps to a specific automated test:

| Spec scenario | Test |
|---|---|
| US1 #1 — instantiate + run `answer_relevancy` + `faithfulness`, get individual scores | `tests/unit/evaluation/test_evaluation_orchestrator.py::test_evaluate_returns_per_metric_results` |
| US1 #2 — all pass → overall `passed` | `tests/unit/evaluation/test_evaluation_result.py::test_passed_true_when_all_metrics_pass` |
| US1 #3 — one fails → overall `failed`, detail identifies which | `tests/unit/evaluation/test_evaluation_result.py::test_passed_false_when_any_metric_fails` |
| US2 #1 — new subclass, zero existing-file changes, instantiable by name | `tests/unit/evaluation/metrics/test_metric_factory_extensibility.py` |
| US2 #2 — unknown name → descriptive error, never `None` | `tests/unit/evaluation/metrics/test_metric_factory.py::test_create_unknown_name_raises` |
| US2 #3 — duplicate canonical name rejected | `tests/unit/evaluation/metrics/test_metric_factory.py::test_register_duplicate_name_raises` |
| US3 #1 — configured threshold overrides native default | `tests/unit/evaluation/test_evaluation_orchestrator.py::test_configured_threshold_applied` |
| US3 #2 — unconfigured bot/metric → native default | `tests/unit/evaluation/test_evaluation_orchestrator.py::test_missing_config_uses_native_default` |
| Edge: metric exception isolated | `tests/unit/evaluation/test_evaluation_orchestrator.py::test_metric_exception_isolated` |
| Edge: metric timeout isolated, no retry | `tests/unit/evaluation/test_evaluation_orchestrator.py::test_metric_timeout_isolated_no_retry` |
| Edge: empty metric list rejected | `tests/unit/evaluation/test_evaluation_orchestrator.py::test_empty_metric_list_rejected` |
| Edge: duplicate names in request rejected | `tests/unit/evaluation/test_evaluation_orchestrator.py::test_duplicate_metric_names_rejected` |
| Edge: invalid threshold/timeout aborts atomically | `tests/unit/evaluation/test_evaluation_orchestrator.py::test_invalid_threshold_aborts_before_any_measure` |
| Edge: `ConfigManager` failure is fail-closed | `tests/unit/evaluation/test_evaluation_orchestrator.py::test_config_manager_failure_aborts` |
| Edge: unknown `bot_id` → native defaults, no abort | `tests/unit/evaluation/test_evaluation_orchestrator.py::test_unknown_bot_id_uses_native_defaults` |

## Manual end-to-end check (optional, requires a real judge API key)

```python
import asyncio
from deepeval_platform.evaluation.evaluation_orchestrator import EvaluationOrchestrator
from deepeval_platform.normalization.models import NormalizedTrace

trace = NormalizedTrace(
    input="What is the refund policy?",
    output="Refunds are available within 30 days of purchase.",
    context=["Our refund policy allows returns within 30 days of purchase."],
    expected_output="Refunds within 30 days.",
)

orchestrator = EvaluationOrchestrator()
result = asyncio.run(
    orchestrator.evaluate(trace=trace, bot_id="test_rag_bot", metric_names=["answer_relevancy", "faithfulness"])
)
print(result.passed, {name: r.score for name, r in result.metrics.items()})
```

**Expected outcome**: `result.metrics` has exactly the two requested keys, each with a numeric
`score` and a `passed` bool; `result.passed` is the AND of both.

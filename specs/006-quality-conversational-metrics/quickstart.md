# Quickstart: Validating Quality/Safety + Conversational Metrics Integration (M3.3)

## Prerequisites

- `uv sync` already run (repo dependencies installed).
- A real judge-LLM API key in `.env` (`OPENAI_API_KEY` / `ANTHROPIC_API_KEY` / `OPENROUTER_API_KEY`)
  **only** for the optional manual end-to-end check below — all unit tests mock the native metric
  and `LLMProviderFactory`, matching the M3.1/M3.2 convention (`tests/conftest.py::mock_env` /
  `mock_config`).

## Automated validation (primary path)

```bash
uv run pytest tests/unit/evaluation -v
uv run pytest --cov=deepeval_platform --cov-report=term-missing --cov-fail-under=80
```

Each acceptance scenario in `spec.md` maps to a specific automated test:

| Spec scenario | Test |
|---|---|
| US1 #1/#2 — `conversation_completeness`/`turn_relevancy` resolve and run via `ConversationStrategy.get_metrics()` | `tests/unit/evaluation/metrics/native/test_conversation_completeness_metric.py`, `test_conversation_relevancy_metric.py` + `tests/unit/evaluation/test_conversation_strategy.py` (updated list assertion) |
| US2 #1/#2 — `bias`/`toxicity` present in all three strategies, `MetricFactory.create()` returns valid instances | `tests/unit/evaluation/metrics/native/test_bias_metric.py`, `test_toxicity_metric.py` + `test_rag_strategy.py`, `test_agent_strategy.py`, `test_conversation_strategy.py` (all updated) |
| US3 #1 — `knowledge_retention`/`role_adherence` run automatically for conversational bots | `tests/unit/evaluation/metrics/native/test_knowledge_retention_metric.py`, `test_role_adherence_metric.py` + `test_conversation_strategy.py` |
| US4 #1–#5 — opt-in metrics activate only when configured, no error when absent | `tests/unit/evaluation/test_bot_metric_config_resolver.py` (new) |
| FR-002/FR-003 — `ConversationalMetricBase` maps `NormalizedTrace.messages` → `Turn` objects; invalid role isolated per-metric | `tests/unit/evaluation/metrics/test_conversational_metric_base.py` (new) |
| FR-010a — `role_adherence` sourced from optional `chatbot_role`; absence isolates (not skips) the metric | `tests/unit/evaluation/metrics/native/test_role_adherence_metric.py` |
| FR-015/FR-016 — resolver has no metric logic; factory forwards options without branching | `tests/unit/evaluation/test_bot_metric_config_resolver.py`, `tests/unit/evaluation/metrics/test_metric_factory.py` (updated) |
| Edge: invalid `Message.role` isolates only conversational metrics, `bias`/`toxicity` unaffected | `tests/unit/evaluation/test_evaluation_orchestrator.py` (new case, mirrors existing per-metric isolation tests) |
| Edge: empty/single-turn `messages` isolates only the five multi-turn-dependent conversational metrics, `bias`/`toxicity` unaffected | `tests/unit/evaluation/test_evaluation_orchestrator.py` (T046a, mirrors the invalid-role isolation test) |
| Edge: malformed opt-in config (bad `json_schema` path, empty `prompt_instructions`) isolates only that metric | `tests/unit/evaluation/test_bot_metric_config_resolver.py` + orchestrator isolation test |

## Manual end-to-end check (optional, requires a real judge API key)

```python
import asyncio
from deepeval_platform.evaluation.evaluation_orchestrator import EvaluationOrchestrator
from deepeval_platform.evaluation.bot_metric_config_resolver import BotMetricConfigResolver
from deepeval_platform.evaluation.strategies.conversation_strategy import ConversationStrategy
from deepeval_platform.normalization.models import Message, NormalizedTrace

conversation_trace = NormalizedTrace(
    input="What's my order status?",
    output="Your order #4471 shipped yesterday and should arrive within 3 business days.",
    messages=[
        Message(role="user", content="Hi, can you check my order?"),
        Message(role="assistant", content="Sure — what's your order number?"),
        Message(role="user", content="It's #4471."),
        Message(role="assistant", content="Your order #4471 shipped yesterday and should arrive within 3 business days."),
    ],
)

resolver = BotMetricConfigResolver()
metric_names = resolver.resolve_metric_names(
    bot_id="test_conversation_bot", strategy_metrics=ConversationStrategy().get_metrics()
)

orchestrator = EvaluationOrchestrator()
result = asyncio.run(
    orchestrator.evaluate(trace=conversation_trace, bot_id="test_conversation_bot", metric_names=metric_names)
)
for name in metric_names:
    print(name, result.metrics[name].score, result.metrics[name].passed, result.metrics[name].error)
```

**Expected outcome**: `metric_names` includes all six `ConversationStrategy` entries
(`conversation_completeness`, `turn_relevancy`, `bias`, `toxicity`, `knowledge_retention`,
`role_adherence`); every entry in `result.metrics` has a numeric `score` and `error is None`,
except `role_adherence` — since `config/bots.yaml`'s `test_conversation_bot` does not declare
`chatbot_role` in this repo's checked-in fixture, that entry is expected to show
`score is None`, `passed is False`, and an error detail naming `MissingTestCaseParamsError`,
demonstrating the FR-008/FR-010a isolated-failure path without needing to edit the fixture file.

# Quickstart: Validating Custom Metrics Integration (GEval, DAG, Ragas) (M3.4)

## Prerequisites

- `uv add "ragas>=0.2.0"` (or `uv sync` once `pyproject.toml` carries the new dependency) — required
  before any Ragas-related test or manual check can import `deepeval_platform.evaluation.metrics.
  native.ragas_metric`.
- A real judge-LLM API key in `.env` (`OPENAI_API_KEY` / `ANTHROPIC_API_KEY` / `OPENROUTER_API_KEY`)
  **only** for the optional manual end-to-end check below — all unit tests mock the native
  `GEval`/`DAGMetric` calls, the Ragas metric's `single_turn_ascore`, and `RagasLLMAdapter`'s
  underlying `DeepEvalBaseLLM`, matching the M3.1-M3.3 convention (`tests/conftest.py::mock_env` /
  `mock_config`).
- For the `dag` manual check specifically: a sample `dag_builder` target module (a zero-argument
  function returning a small valid `DeepAcyclicGraph`) reachable on `sys.path` — the fixture bot
  config points at it by dotted path.

## Automated validation (primary path)

```bash
uv run pytest tests/unit/evaluation -v
uv run pytest tests/unit/llm/test_ragas_adapter.py -v
uv run pytest --cov=deepeval_platform --cov-report=term-missing --cov-fail-under=80
```

Each acceptance scenario in `spec.md` maps to a specific automated test:

| Spec scenario | Test |
|---|---|
| US1 #1/#2/#3 — `g_eval` runs with bot-declared `geval_criteria`, registers cleanly via `MetricFactory.create("g_eval", ...)`, is never attempted when `geval_criteria` is absent | `tests/unit/evaluation/metrics/native/test_g_eval_metric.py` + `tests/unit/evaluation/test_bot_metric_config_resolver.py` (new `geval_criteria` cases) |
| US2 #1/#2/#3 — `dag` runs with a bot-declared `dag_builder`, registers cleanly via `MetricFactory.create("dag", ...)`, is never attempted when `dag_builder` is absent | `tests/unit/evaluation/metrics/native/test_dag_metric.py` + `tests/unit/evaluation/test_bot_metric_config_resolver.py` (new `dag_builder` cases, including the invoke-not-use-as-is assertion) |
| US3 #1/#2/#3 — both Ragas metrics run when opted in, register cleanly via `MetricFactory.create()`, are never attempted when not opted in | `tests/unit/evaluation/metrics/native/test_ragas_metric.py` + `tests/unit/evaluation/test_bot_metric_config_resolver.py` (new `ragas_*.enabled` cases) |
| FR-009 — `RagasLLMAdapter` adapts the bot's existing `DeepEvalBaseLLM` judge without touching `LLMProviderFactory` | `tests/unit/llm/test_ragas_adapter.py` (new) |
| FR-014 — Ragas Answer Correctness embeddings reuse global `embedding.model`/`embedding.dimensions`, same `OpenAIEmbeddings` construction as `QdrantVectorStoreProvider` | `tests/unit/evaluation/metrics/native/test_ragas_metric.py` (embeddings-construction case) |
| Edge: empty/malformed `g_eval` criteria isolates only `g_eval` | `tests/unit/evaluation/test_evaluation_orchestrator.py` (new case, mirrors existing per-metric isolation tests) |
| Edge: invalid `dag` definition (cycle/orphan/broken reference) isolates only `dag` | `tests/unit/evaluation/test_evaluation_orchestrator.py` (new case) |
| Edge: `ragas` package/config missing or a Ragas metric's `measure()` raising/timing out isolates only that Ragas metric | `tests/unit/evaluation/test_evaluation_orchestrator.py` (new case) + `tests/unit/evaluation/metrics/native/test_ragas_metric.py` |
| Edge: all four new metrics enabled simultaneously run independently, no cross-blocking | `tests/unit/evaluation/test_evaluation_orchestrator.py` (new case, mirrors M3.3's multi-opt-in isolation test) |
| SC-005 — `MetricFactory.register()`/`create()`, `EvaluationContext`, `EvaluationResult` unchanged | covered structurally — no test file for these classes is modified by this feature |

## Manual end-to-end check (optional, requires a real judge API key)

```python
import asyncio
from deepeval_platform.evaluation.evaluation_orchestrator import EvaluationOrchestrator
from deepeval_platform.evaluation.bot_metric_config_resolver import BotMetricConfigResolver
from deepeval_platform.evaluation.strategies.rag_strategy import RAGStrategy
from deepeval_platform.normalization.models import NormalizedTrace

rag_trace = NormalizedTrace(
    input="What's your refund policy?",
    output="Refunds are available within 7 days of purchase with a valid receipt.",
    expected_output="Refunds are available within 7 days of purchase with proof of purchase.",
    context=[
        "Our refund policy allows returns within 7 days of purchase.",
        "A valid receipt or proof of purchase is required for all refunds.",
    ],
)

resolver = BotMetricConfigResolver()
metric_names = resolver.resolve_metric_names(
    bot_id="test_rag_bot", strategy_metrics=RAGStrategy().get_metrics()
)

orchestrator = EvaluationOrchestrator()
result = asyncio.run(
    orchestrator.evaluate(trace=rag_trace, bot_id="test_rag_bot", metric_names=metric_names)
)
for name in metric_names:
    print(name, result.metrics[name].score, result.metrics[name].passed, result.metrics[name].error)
```

**Expected outcome**: `metric_names` includes every `RAGStrategy` entry plus `g_eval`, `dag`,
`ragas_answer_correctness`, and `ragas_context_recall` — but only if `config/bots.yaml`'s
`test_rag_bot` declares `geval_criteria`, `dag_builder`, and both `ragas_*.enabled: true` (per the
Configuration surface addition documented in `contracts/evaluation-api.md`); if any of those keys
is absent for this bot, the corresponding name is simply missing from `metric_names` — no error.
Every present entry in `result.metrics` has a numeric `score` and `error is None`, demonstrating
the opt-in-activation and independent-execution guarantees (SC-001-SC-004) without needing a
special failure fixture.

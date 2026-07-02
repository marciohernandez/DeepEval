# Quickstart Validation Guide: M1 — Foundation and Infrastructure

**Phase**: 1 | **Date**: 2026-06-25 | **Feature**: 001-m1-foundation-infrastructure

This guide describes how to verify that all six M1 foundation modules are working end-to-end
in a local development environment. It is a validation guide — not a tutorial or implementation
reference. Full implementation details are in `tasks.md` and the contracts.

---

## Prerequisites

### 1. Running services

| Service | Where | Check |
|---------|-------|-------|
| Langfuse | Self-hosted VPS | `curl http://<LANGFUSE_HOST>/api/health` returns `200` |
| Qdrant | Self-hosted VPS | `curl http://<QDRANT_HOST>:<QDRANT_PORT>/healthz` returns `{"title":"qdrant - main"}` |
| Supabase | Cloud (supabase.com) | Project URL accessible from dev machine |

### 2. Credentials

Populate `.env` from `.env.example` (see [contracts/config_manager.py](contracts/config_manager.py)
for required keys). The following groups are needed for M1:

```
LANGFUSE_HOST, LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY
QDRANT_HOST, QDRANT_PORT, QDRANT_API_KEY
SUPABASE_URL, SUPABASE_SERVICE_KEY
OPENAI_API_KEY, OPENAI_DEFAULT_MODEL         (for LLMProviderFactory + embeddings)
ANTHROPIC_API_KEY, ANTHROPIC_DEFAULT_MODEL   (optional, to test AnthropicProvider)
OPENROUTER_API_KEY, OPENROUTER_DEFAULT_MODEL (optional, to test OpenRouterProvider)
```

### 3. Config files

Ensure `config/settings.yaml` contains:
```yaml
embedding:
  model: text-embedding-3-small
  dimensions: 1536
```

### 4. Database table

Run the SQL in [data-model.md](data-model.md) (`evaluation_results` schema) in the Supabase
SQL editor to create the table before running EvaluationRepository validation.

### 5. Python environment

```bash
uv sync
```

---

## Validation Scenarios

### Scenario 1 — ConfigManager (FR-001, FR-002, FR-003, FR-004)

```bash
uv run python -c "
from deepeval.config import ConfigManager, ConfigError

cfg = ConfigManager.instance()

# FR-001: Read values from .env and YAML via single accessor
host = cfg.get('LANGFUSE_HOST')
model = cfg.get('embedding.model')
print(f'Langfuse host: {host}')
print(f'Embedding model: {model}')

# FR-002: Same instance on second call
cfg2 = ConfigManager.instance()
assert cfg is cfg2, 'Singleton violated'
print('Singleton: OK')

# FR-004: Sensitive keys masked in repr
print(repr(cfg))  # should NOT show LANGFUSE_SECRET_KEY value

# FR-003: Missing key raises descriptive error
try:
    cfg.get('NONEXISTENT_KEY')
except ConfigError as e:
    print(f'ConfigError (expected): {e}')
"
```

**Expected**: Values printed, no secrets visible in repr, `ConfigError` raised with key name
and expected source file. No re-read of files on second call.

---

### Scenario 2 — LangfuseClient (FR-005, FR-006, FR-007)

```bash
uv run python -c "
from deepeval.observability import LangfuseClient, TelemetryEvent
from datetime import datetime, timezone

client = LangfuseClient.instance()

# FR-005: Singleton connection
client2 = LangfuseClient.instance()
assert client is client2, 'Singleton violated'
print('Singleton: OK')

# FR-005 + FR-007: Submit a synthetic event
event = TelemetryEvent(
    session_id='test-session-001',
    name='validation-trace',
    input={'text': 'hello'},
    output={'text': 'world'},
    metadata={'source': 'quickstart'},
    start_time=datetime.now(timezone.utc),
)
client.submit(event)
print('Event submitted — check Langfuse UI for trace: validation-trace / session test-session-001')

# FR-006: Flush (will be called automatically on exit via atexit, but call explicitly here)
client.flush()
print('Flush: OK')
"
```

**Expected**: No crash on submit. After running, open Langfuse UI and confirm a trace named
`validation-trace` with session `test-session-001` appears within 30 seconds (SC-007).

---

### Scenario 3 — QdrantVectorStoreProvider (FR-008, FR-009)

```bash
uv run python -c "
from deepeval.vector_store import QdrantVectorStoreProvider
from langchain_core.documents import Document

provider = QdrantVectorStoreProvider.instance()

# FR-008: Auto-create collection
store = provider.get_store('m1-quickstart-test')
print('Store obtained: OK')

# FR-009: Add document and retrieve
doc = Document(page_content='The capital of France is Paris.', metadata={'source': 'quickstart'})
store.add_documents([doc])
results = store.similarity_search('What is the capital of France?', k=1)
assert len(results) == 1
assert 'Paris' in results[0].page_content
print(f'Retrieved: {results[0].page_content[:60]}')

# FR-009: LangChain retriever compatibility
retriever = store.as_retriever()
print(f'Retriever type: {type(retriever).__name__}')

# Cleanup
provider.delete_collection('m1-quickstart-test')
print('Cleanup: OK')
"
```

**Expected**: Collection created, document added, semantic search returns the Paris document.
`retriever` is a `VectorStoreRetriever` instance usable in LangGraph/LangChain chains.

---

### Scenario 4 — LLMProviderFactory (FR-010, FR-011, FR-012)

```bash
uv run python -c "
from deepeval.llm import LLMProviderFactory, LLMProviderError

# FR-010: Create all three providers
for provider_name in ['openai', 'anthropic', 'openrouter']:
    try:
        provider = LLMProviderFactory.create(provider_name)
        # FR-010: Execute a simple completion
        response, usage = provider.generate('Say PASS in one word.')
        print(f'{provider_name}: {response.strip()[:20]}')
    except LLMProviderError as e:
        print(f'{provider_name}: skipped (missing credential) — {e}')

# FR-012: Unsupported provider raises descriptive error
try:
    LLMProviderFactory.create('unsupported-provider')
except LLMProviderError as e:
    print(f'Unsupported provider error (expected): {e}')
    assert 'openai' in str(e).lower(), 'Error should list supported providers'
"
```

**Expected**: Each configured provider returns a short completion. Unsupported provider
raises `LLMProviderError` that names the unsupported value and lists supported options.

---

### Scenario 5 — TraceRepository (FR-013, FR-014)

Requires at least one trace to exist in Langfuse (run Scenario 2 first).

```bash
uv run python -c "
from deepeval.repositories import TraceRepository

repo = TraceRepository()

# FR-013: Query by session
traces = repo.get_by_session('test-session-001')
print(f'Traces found: {len(traces)}')

if traces:
    t = traces[0]
    # FR-014: Structured TraceRecord, not raw API response
    print(f'  trace_id: {t.trace_id}')
    print(f'  bot_id: {t.bot_id}')
    print(f'  input: {t.input}')
    print(f'  output: {t.output}')

# FR-013: Empty result is not an error
empty = repo.get_by_session('nonexistent-session-xyz')
assert empty == []
print('Empty result: OK')
"
```

**Expected**: The trace from Scenario 2 is returned as a structured `TraceRecord`.
No raw Langfuse response objects appear. Empty session returns `[]`.

---

### Scenario 6 — EvaluationRepository (FR-015, FR-016, FR-017)

```bash
uv run python -c "
import uuid
from datetime import datetime, timezone
from deepeval.repositories import EvaluationRepository
from deepeval.repositories.evaluation_repository import EvaluationResult

repo = EvaluationRepository()

# FR-015: Application-generated UUID
result = EvaluationResult(
    id=uuid.uuid4(),
    bot_id='test-bot',
    trace_id=None,
    metric_name='answer_relevancy',
    score=0.92,
    passed=True,
    threshold=0.7,
    reason='Answer is highly relevant.',
    metadata={'source': 'quickstart'},
    org_id=None,                  # FR-016: nullable org_id always included
    created_at=datetime.now(timezone.utc),
)

saved_id = repo.save(result)
print(f'Saved result id: {saved_id}')
assert saved_id == result.id, 'ID mismatch'

# Retrieve and verify
retrieved = repo.get_by_id(saved_id)
assert retrieved.bot_id == 'test-bot'
assert retrieved.score == 0.92
assert retrieved.org_id is None          # FR-016: org_id persisted as NULL
print(f'Retrieved: bot_id={retrieved.bot_id}, score={retrieved.score}, org_id={retrieved.org_id}')
print('Persistence round-trip: OK')
"
```

**Expected**: Result is persisted with the application-generated UUID, `org_id=None` is stored
(not omitted), and retrieved record matches all fields exactly.

---

## Full Round-Trip (SC-005)

After all six scenarios pass individually, run the end-to-end scenario.

> **M1 scope note**: "run evaluation" in SC-005 means scoring via `LLMProviderFactory` + `generate()`.
> Full DeepEval metric invocation (`AnswerRelevancyMetric`, etc.) is out of scope for M1 — it will
> be wired in a future milestone once the evaluation pipeline is implemented.

```bash
uv run python -c "
# Read trace → create LLM judge → persist result
import uuid
from datetime import datetime, timezone
from deepeval.repositories import TraceRepository, EvaluationRepository
from deepeval.repositories.evaluation_repository import EvaluationResult
from deepeval.llm import LLMProviderFactory

# Step 1: Read trace
trace_repo = TraceRepository()
traces = trace_repo.get_by_session('test-session-001')
trace = traces[0] if traces else None

# Step 2: LLM judge (simulate scoring)
judge = LLMProviderFactory.create('openai')
response, _ = judge.generate(f'Rate relevance 0-1 for: {trace.input if trace else \"hello\"}')
score = 0.9  # synthetic for quickstart

# Step 3: Persist result
eval_repo = EvaluationRepository()
result = EvaluationResult(
    id=uuid.uuid4(),
    bot_id='test-bot',
    trace_id=trace.trace_id if trace else None,
    metric_name='answer_relevancy',
    score=score,
    passed=score >= 0.7,
    threshold=0.7,
    reason=response[:200],
    metadata={},
    org_id=None,
    created_at=datetime.now(timezone.utc),
)
saved_id = eval_repo.save(result)
print(f'Round-trip complete. Result persisted: {saved_id}')
"
```

**Expected**: Completes without error. Result visible in Supabase `evaluation_results` table.

---

## Unit Test Suite

After implementation, run the full test suite to verify ≥ 80% coverage (SC-003):

```bash
uv run pytest tests/ --cov=deepeval --cov-report=term-missing --cov-fail-under=80 -v
```

**Expected**: All tests pass, coverage ≥ 80% for all modules under `deepeval/`.

---

## Links

- [Data Model](data-model.md) — entity definitions and DB schema
- [Contracts](contracts/) — public interface specifications per module
- [Research](research.md) — LangChain MCP findings and dependency decisions
- [Plan](plan.md) — implementation plan

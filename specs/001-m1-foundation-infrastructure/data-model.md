# Data Model: M1 — Foundation and Infrastructure

**Phase**: 1 | **Date**: 2026-06-25 | **Feature**: 001-m1-foundation-infrastructure

## Entities

### ConfigEntry

Represents a single configuration value resolved from `.env` or `config/*.yaml`.

| Field | Type | Notes |
|-------|------|-------|
| `key` | `str` | Dot-notation key (e.g., `langfuse.host`, `LANGFUSE_HOST`) |
| `value` | `str` | Resolved value; never empty string (treated as missing) |
| `source` | `Literal["env", "yaml"]` | File source that provided the value |
| `source_file` | `str` | Filename (e.g., `.env`, `config/settings.yaml`) |
| `is_sensitive` | `bool` | True if key contains `key`, `secret`, `password`, `token`, `api` |

**Validation rules**:
- `value` must be non-empty string; empty string raises `ConfigError` (FR-003)
- `is_sensitive` keys are masked (`***`) in `__repr__` and any log output (FR-004)
- `.env` values take precedence over YAML values for the same key (merge priority)

**State**: Immutable after load. `ConfigManager` rejects re-load after first access (FR-002).

---

### TelemetryEvent

Represents a single trace or span event submitted to the Langfuse observability platform.

| Field | Type | Notes |
|-------|------|-------|
| `session_id` | `str` | Langfuse session identifier |
| `trace_id` | `str \| None` | Langfuse trace ID if known at submission |
| `name` | `str` | Event name / span name |
| `input` | `dict \| str \| None` | Input payload for the trace/span |
| `output` | `dict \| str \| None` | Output payload; may be `None` (e.g., interrupted session) |
| `metadata` | `dict` | Arbitrary key-value metadata |
| `start_time` | `datetime \| None` | Start timestamp (UTC) |
| `end_time` | `datetime \| None` | End timestamp (UTC) |

**Notes**: `TelemetryEvent` is a value object used as input to `LangfuseClient.submit()`.
The actual Langfuse SDK trace/span objects are created internally; this entity is never
persisted directly by our code.

---

### VectorCollection

Represents a named collection in the Qdrant vector store.

| Field | Type | Notes |
|-------|------|-------|
| `name` | `str` | Collection name (must be valid Qdrant collection identifier) |
| `embedding_model` | `str` | Embedding model name (sourced from `config/settings.yaml`) |
| `embedding_dimensions` | `int` | Vector dimensions (sourced from `config/settings.yaml`) |
| `created_at` | `datetime \| None` | Set when collection is first created; `None` if pre-existing |

**Validation rules**:
- `name` must match `^[a-zA-Z0-9_-]+$`; invalid names raise `VectorStoreError`
- `embedding_model` and `embedding_dimensions` are global V1 values — all collections share
  the same model (FR-008, confirmed in Clarifications 2026-06-25)
- Collection is created automatically if absent; reused if exists (FR-008)

**State**: The `QdrantVectorStoreProvider` maintains an internal cache of provisioned
`VectorCollection` names to avoid redundant collection checks (Singleton principle, FR-009).

---

### LLMProviderInstance

Represents a ready-to-use language model handle that implements `DeepEvalBaseLLM`.

| Field | Type | Notes |
|-------|------|-------|
| `provider` | `Literal["openai", "anthropic", "openrouter"]` | Provider identifier |
| `model` | `str` | Model name (e.g., `gpt-4o-mini`, `claude-haiku-4-5-20251001`) |
| `_lc_model` | `BaseChatModel` | Internal LangChain chat model instance (private) |

**Validation rules**:
- `provider` must be one of the supported values; unsupported raises `LLMProviderError`
  with a list of supported options (FR-012)
- API credentials sourced exclusively from `ConfigManager` — never passed as constructor args (FR-011)
- Missing credential raises `LLMProviderError` naming the missing key and its config location (FR-011)

**Supported providers**:

| Provider | LangChain Class | Package |
|----------|----------------|---------|
| `openai` | `ChatOpenAI` | `langchain-openai` |
| `anthropic` | `ChatAnthropic` | `langchain-anthropic` |
| `openrouter` | `ChatOpenRouter` | `langchain-openrouter` |

**Extension rule**: Adding a new provider requires only a new `LLMProviderBase` subclass and
registration in `LLMProviderFactory._registry`. Zero changes to existing code (SC-006).

---

### TraceRecord

Represents a structured single bot interaction trace read from Langfuse.

| Field | Type | Notes |
|-------|------|-------|
| `trace_id` | `str` | Langfuse trace ID (primary key from Langfuse) |
| `session_id` | `str \| None` | Langfuse session ID |
| `bot_id` | `str` | Bot identifier (maps to `bot_name` tag in Langfuse) |
| `input` | `dict \| str` | User input for the interaction |
| `output` | `dict \| str \| None` | Bot response; `None` for interrupted sessions |
| `metadata` | `dict` | Trace-level metadata from Langfuse |
| `start_time` | `datetime` | Trace start timestamp (UTC) |
| `end_time` | `datetime \| None` | Trace end timestamp; `None` if session still open |

**Validation rules**:
- `output` may be `None` for interrupted sessions — callers must handle this case (Edge Case)
- Raw Langfuse API responses are never exposed; all fields mapped to this entity (FR-014)
- Empty result set (no traces match) returns `[]` without error (FR-013)

**State**: Read-only value object. Not persisted by this system (traces live in Langfuse).

---

### EvaluationResult

Represents a persisted evaluation record in the relational database (Supabase).

| Field | Type | Notes |
|-------|------|-------|
| `id` | `UUID` | Application-generated `uuid.uuid4()` before insert (FR-015) |
| `bot_id` | `str` | Bot identifier |
| `trace_id` | `str \| None` | Reference to the evaluated Langfuse trace |
| `metric_name` | `str` | Name of the DeepEval metric (e.g., `answer_relevancy`) |
| `score` | `float` | Numeric score `[0.0, 1.0]` |
| `passed` | `bool` | Whether score meets the metric threshold |
| `threshold` | `float` | Threshold used for pass/fail determination |
| `reason` | `str \| None` | Explanation from the LLM judge (nullable) |
| `metadata` | `dict` | Arbitrary key-value metadata for this result |
| `org_id` | `UUID \| None` | Nullable; reserved for V2 multi-tenant activation (FR-016) |
| `created_at` | `datetime` | Set at application layer before insert (UTC) |

**Validation rules**:
- `id` is generated by the application (`uuid.uuid4()`) before the DB insert; caller knows
  the ID without a DB round-trip (FR-015)
- `org_id` is always included in the insert, even if `None` (FR-016)
- DB write failure raises `RepositoryError` — no silent data loss (FR-017)

**Database table**: `evaluation_results` (Supabase)

**Schema** (Supabase SQL):
```sql
CREATE TABLE evaluation_results (
    id          UUID PRIMARY KEY,
    bot_id      TEXT NOT NULL,
    trace_id    TEXT,
    metric_name TEXT NOT NULL,
    score       FLOAT NOT NULL,
    passed      BOOLEAN NOT NULL,
    threshold   FLOAT NOT NULL,
    reason      TEXT,
    metadata    JSONB DEFAULT '{}',
    org_id      UUID,
    created_at  TIMESTAMPTZ NOT NULL
);
```

---

## Entity Relationships

```
ConfigManager ──────────────────────────────────────────────────── all modules
    │ provides credentials + settings
    ▼
LangfuseClient (Singleton)          QdrantVectorStoreProvider (Singleton)
    │ uses Langfuse SDK                  │ uses langchain_qdrant.QdrantVectorStore
    │                                    │ uses OpenAIEmbeddings
    ▼                                    ▼
TelemetryEvent ──► Langfuse      VectorCollection ──► Qdrant

LLMProviderFactory
    │ creates
    ▼
LLMProviderInstance (OpenAI / Anthropic / OpenRouter)
    │ wraps LangChain ChatModel
    │ implements DeepEvalBaseLLM

TraceRepository
    │ reads from Langfuse via SDK
    ▼
TraceRecord[]

EvaluationRepository
    │ writes to Supabase
    ▼
EvaluationResult
```

---

## Module → Source File Mapping

| Entity | Module | File |
|--------|--------|------|
| `ConfigEntry` | `config` | `deepeval/config/config_manager.py` |
| `TelemetryEvent` | `observability` | `deepeval/observability/langfuse_client.py` |
| `VectorCollection` | `vector_store` | `deepeval/vector_store/qdrant_provider.py` |
| `LLMProviderInstance` | `llm` | `deepeval/llm/base.py` + `deepeval/llm/factory.py` |
| `TraceRecord` | `repositories` | `deepeval/repositories/trace_repository.py` |
| `EvaluationResult` | `repositories` | `deepeval/repositories/evaluation_repository.py` |

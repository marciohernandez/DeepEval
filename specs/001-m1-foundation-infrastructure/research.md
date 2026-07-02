# Research: M1 — Foundation and Infrastructure

**Phase**: 0 | **Date**: 2026-06-25 | **Feature**: 001-m1-foundation-infrastructure

## LangChain MCP Consultation (Constitution Principle II)

The LangChain MCP was consulted before any implementation decisions were made. Findings below
are authoritative and override assumptions derived from prior knowledge.

---

### Finding 1 — QdrantVectorStoreProvider

**Question**: Does LangChain provide a native Qdrant integration for Python?

**Decision**: Use `langchain_qdrant.QdrantVectorStore` from package `langchain-qdrant`.

**Rationale**: Native integration confirmed in LangChain docs. Provides `add_documents`,
`similarity_search`, and `.as_retriever()` out of the box — all required by FR-008/FR-009.
Using any custom Qdrant wrapper would violate Principle II.

**Alternatives considered**: `qdrant-client` raw SDK — rejected; native LangChain integration
exists and must be used per Principle II.

**Embedding model**: `OpenAIEmbeddings` from `langchain-openai` — confirmed native integration.
Single global model configured in `config/settings.yaml` (`embedding.model` + `embedding.dimensions`).
Default: `text-embedding-3-small` (1536 dims). `QdrantVectorStoreProvider` reads model name
from `ConfigManager` and instantiates `OpenAIEmbeddings` internally.

**Package**: `langchain-qdrant` (add via `uv add langchain-qdrant`)

---

### Finding 2 — LLMProviderFactory / OpenRouter

**Question**: Should OpenRouter use `ChatOpenAI` with custom `base_url`, or a dedicated integration?

**Decision**: Use `ChatOpenRouter` from `langchain-openrouter` for the OpenRouter provider.
Use `ChatOpenAI` from `langchain-openai` for OpenAI.
Use `ChatAnthropic` from `langchain-anthropic` for Anthropic.

**Rationale**: LangChain docs explicitly state:
> "For OpenRouter, prefer the dedicated integration `ChatOpenRouter`"
> "Non-standard response fields from third-party providers are not extracted or preserved [by ChatOpenAI]."

`ChatOpenRouter` is a first-class LangChain integration (`langchain-openrouter` package) and must
be used over the `ChatOpenAI + base_url` workaround described in the initial tech_stack.md.
This updates the approach in `tech_stack.md §2.8`.

**Wrapping strategy**: Each `LLMProviderBase` subclass holds an internal `_lc_model` attribute
(the LangChain chat model) and implements `DeepEvalBaseLLM` by delegating to it. This gives
DeepEval metrics a compliant judge interface while the underlying LangChain model remains
available for orchestration use cases.

**Alternatives considered**:
- `ChatOpenAI` with `base_url` for OpenRouter — rejected; LangChain docs warn against it for
  non-standard provider fields; dedicated package exists.
- Raw provider SDKs (openai, anthropic) — rejected; LangChain native classes exist (Principle II).

**Packages**:
- `langchain-openai` — `ChatOpenAI`, `OpenAIEmbeddings`
- `langchain-anthropic` — `ChatAnthropic`
- `langchain-openrouter` — `ChatOpenRouter`

---

### Finding 3 — ConfigManager

**Question**: Does LangChain provide any configuration management component?

**Decision**: No native LangChain equivalent exists. Implement custom `ConfigManager` Singleton
using `python-dotenv` + `PyYAML`.

**Rationale**: No LangChain class covers the combined .env + YAML loading pattern with
Singleton semantics and masking requirement. Custom implementation is permitted per Principle II
when no native option exists.

**Merge priority**: `.env` takes precedence over `config/settings.yaml` when the same key
appears in both (standard dotenv convention, confirmed in spec Assumptions).

**Empty string policy**: An empty string value is treated identically to a missing key —
raises FR-003 descriptive error (confirmed in spec Clarifications 2026-06-25).

**Sensitive key detection**: Keys containing any of `key`, `secret`, `password`, `token`,
`api` (case-insensitive) are classified as sensitive and masked in `__repr__` / logging.

---

### Finding 4 — LangfuseClient

**Question**: Does LangChain provide a Langfuse singleton wrapper?

**Decision**: No LangChain equivalent. `LangfuseClient` wraps the Langfuse Python SDK directly
(`langfuse>=4.9.1`). Singleton pattern prevents multiple SDK client instances.

**Shutdown flush**: Registered via `atexit.register(client.flush)` at singleton creation time.
Delegates all retry/back-off to the Langfuse SDK's built-in async flush mechanism (FR-007).

**Alternatives considered**: Custom retry layer — rejected; spec explicitly delegates to SDK
(FR-007, Clarification 2026-06-25).

---

### Finding 5 — TraceRepository

**Question**: Does LangChain provide a trace-reading abstraction for Langfuse?

**Decision**: No LangChain equivalent. `TraceRepository` uses the Langfuse Python SDK's
`langfuse.api` module to fetch traces by bot identifier, date range, and session ID.

**Rationale**: Langfuse trace reading is Langfuse SDK territory, not LangChain territory.
The Repository pattern isolates SDK calls behind a clean interface (FR-013/FR-014).

---

### Finding 6 — EvaluationRepository

**Question**: Does LangChain provide a persistence abstraction for evaluation results?

**Decision**: No LangChain equivalent. `EvaluationRepository` uses the Supabase Python SDK
(`supabase>=2.0.0`) table/insert/select API directly.

**UUID strategy**: Application-generated `uuid.uuid4()` before insert — ID is available to
the caller without a DB round-trip (FR-015, confirmed in Clarifications 2026-06-25).

**org_id**: Included as a nullable column in every insert (FR-016).

---

## Dependency Resolution

Final M1 Python dependencies to add via `uv add`:

| Package | Version | Purpose |
|---------|---------|---------|
| `python-dotenv` | `^1.0.0` | ConfigManager: .env loading |
| `PyYAML` | `^6.0` | ConfigManager: YAML loading |
| `langfuse` | `^4.9.1` | LangfuseClient + TraceRepository |
| `langchain-qdrant` | latest `^0.x` | QdrantVectorStoreProvider (LangChain-first) |
| `langchain-openai` | latest `^0.x` | OpenAIProvider + OpenAIEmbeddings |
| `langchain-anthropic` | latest `^0.x` | AnthropicProvider |
| `langchain-openrouter` | latest `^0.x` | OpenRouterProvider (dedicated, not base_url hack) |
| `supabase` | `^2.0.0` | EvaluationRepository |
| `deepeval` | `^4.0.6` | DeepEvalBaseLLM interface for LLMProviderBase |
| `pytest` | `^8.0.0` | TDD framework |
| `pytest-cov` | `^5.0.0` | Coverage enforcement ≥ 80% |
| `pytest-asyncio` | `^0.23.0` | Async tests |
| `pytest-mock` | `^3.14.0` | Isolation mocks |

Note: `qdrant-client` is a transitive dependency of `langchain-qdrant` — do not add directly.
`langchain-core` and `langchain` are transitive dependencies — do not add directly.

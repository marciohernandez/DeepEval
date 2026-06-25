# Tasks: M1 — Foundation and Infrastructure

**Input**: Design documents from `/specs/001-m1-foundation-infrastructure/`

**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅, contracts/ ✅, quickstart.md ✅

**TDD**: Tests are **NON-NEGOTIABLE** per constitution Principle III. Test tasks are always marked RED — write them first and verify they FAIL before any implementation begins.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependency on incomplete tasks in the same phase)
- **[Story]**: Which user story this task belongs to (US1–US6)
- Exact file paths are included in all task descriptions

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Create the package skeleton, install all dependencies, and set up non-sensitive config files.

- [ ] T001 Create `deepeval/` package tree with all subdirectories (`config/`, `observability/`, `vector_store/`, `llm/`, `repositories/`) and empty `__init__.py` files in each; create `tests/unit/config/`, `tests/unit/observability/`, `tests/unit/vector_store/`, `tests/unit/llm/`, `tests/unit/repositories/`, `tests/integration/` directories with `__init__.py` stubs
- [ ] T002 Add M1 runtime dependencies to `pyproject.toml` via: `uv add python-dotenv PyYAML langfuse langchain-qdrant langchain-openai langchain-anthropic langchain-openrouter "supabase>=2.0.0" "deepeval>=4.0.6"`
- [ ] T003 Add M1 test dependencies to `pyproject.toml` via: `uv add --dev pytest pytest-cov pytest-asyncio pytest-mock`
- [ ] T004 Add `[tool.pytest.ini_options]` section to `pyproject.toml` with `asyncio_mode = "auto"`, `testpaths = ["tests"]`, and `addopts = "--cov=deepeval --cov-report=term-missing --cov-fail-under=80"`
- [ ] T005 [P] Create `config/settings.yaml` with `embedding: {model: text-embedding-3-small, dimensions: 1536}`; create empty stub `config/bots.yaml` and `config/personas.yaml`
- [ ] T006 [P] Create `.env.example` listing all required keys with no values: `LANGFUSE_HOST`, `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `QDRANT_HOST`, `QDRANT_PORT`, `QDRANT_API_KEY`, `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, `OPENAI_API_KEY`, `OPENAI_DEFAULT_MODEL`, `ANTHROPIC_API_KEY`, `ANTHROPIC_DEFAULT_MODEL`, `OPENROUTER_API_KEY`, `OPENROUTER_DEFAULT_MODEL`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Shared test infrastructure that ALL unit test phases depend on. Must be complete before any user story test tasks.

**⚠️ CRITICAL**: No user story test tasks can be written until this phase is complete.

- [ ] T007 Create `tests/conftest.py` with a `mock_env` fixture (patches `os.environ` with safe test credential stubs for all M1 keys) and a `mock_config` fixture (returns a pre-configured stub `ConfigManager` instance using `pytest-mock`); these fixtures are imported automatically by all unit tests via pytest discovery

**Checkpoint**: Package skeleton and test infrastructure ready — user story phases can now begin

---

## Phase 3: User Story 1 — Secure Centralized Configuration (Priority: P1) 🎯 MVP

**Goal**: `ConfigManager` singleton loads `.env` and `config/*.yaml` exactly once, enforces non-empty values, and masks sensitive keys in all output.

**Independent Test**: `ConfigManager.instance()` returns correct values from `.env` and `settings.yaml`; second call returns the same instance (no re-read); missing or empty-string key raises `ConfigError` naming the key and expected source file; sensitive keys are masked (`***`) in `repr()`.

### Tests for User Story 1 — Write FIRST, verify RED before T010

> **RED**: Run `uv run pytest tests/unit/config/ -v` after T008 — ALL tests must FAIL (no source yet)

- [ ] T008 [P] [US1] Write unit tests in `tests/unit/config/test_config_manager.py` covering: singleton `instance()` returns same object on repeated calls, `.env` value loaded correctly, `config/settings.yaml` value loaded via dot-notation key, `.env` takes precedence over YAML for the same key, absent key raises `ConfigError` with key name and source file in message, empty-string value raises `ConfigError` identically to absent key, sensitive key masked as `***` in `ConfigEntry.__repr__()` and `ConfigManager.__repr__()`, `get_optional()` returns default when key absent, `get_typed()` casts value to expected type and raises `ConfigError` on cast failure
- [ ] T009 [P] [US1] Write integration tests in `tests/integration/test_config_manager_integration.py` covering: real `.env` file loaded end-to-end, real `config/settings.yaml` loaded via dot-notation, singleton stable across separate `import` statements in same process

### Implementation for User Story 1

- [ ] T010 [US1] Implement `ConfigEntry` dataclass with fields `key: str`, `value: str`, `source: Literal["env", "yaml"]`, `source_file: str`, `is_sensitive: bool`, and `__repr__()` that masks `value` as `***` when `is_sensitive` is True — in `deepeval/config/config_manager.py`
- [ ] T011 [US1] Implement `ConfigError` exception class that accepts `key` and `source_file` and formats a descriptive message naming both — in `deepeval/config/config_manager.py`
- [ ] T012 [US1] Implement `ConfigManager` Singleton class with `_instance: ClassVar`, `_loaded: bool` guard, and `instance()` classmethod that loads `.env` via `python-dotenv` and all `config/*.yaml` files via `PyYAML` with `.env` values taking precedence over YAML on key collision — in `deepeval/config/config_manager.py`
- [ ] T013 [US1] Implement `ConfigManager.get(key: str) -> str` that raises `ConfigError` when key is absent or has an empty string value (both treated identically per FR-003), with error message naming the key and expected source file — in `deepeval/config/config_manager.py`
- [ ] T014 [US1] Implement `ConfigManager.get_optional(key, default="") -> str` returning `default` when key absent, and `ConfigManager.get_typed(key, expected_type) -> Any` casting to type and raising `ConfigError` on failure — in `deepeval/config/config_manager.py`
- [ ] T015 [US1] Implement sensitive key detection in `ConfigEntry`: classify `is_sensitive=True` when key contains any of `key`, `secret`, `password`, `token`, `api` (case-insensitive); implement `ConfigManager.__repr__()` that masks all sensitive entries — in `deepeval/config/config_manager.py`; export `ConfigManager`, `ConfigError`, `ConfigEntry` from `deepeval/config/__init__.py`

**Checkpoint**: `uv run pytest tests/unit/config/ -v` must be GREEN (all pass). User Story 1 is independently testable.

---

## Phase 4: User Story 2 — Reliable Observability Telemetry (Priority: P2)

**Goal**: `LangfuseClient` singleton wraps the Langfuse Python SDK, submits telemetry events asynchronously, flushes on shutdown via `atexit`, and logs a warning (never crashes) when the platform is unreachable.

**Independent Test**: `client.submit(event)` queues event without raising; `flush()` blocks until sent; `atexit` is registered at singleton creation; `is_connected()` returns `True` after init; connectivity warning is logged when SDK raises on submit.

### Tests for User Story 2 — Write FIRST, verify RED before T018

> **RED**: Run `uv run pytest tests/unit/observability/ -v` after T016 — ALL tests must FAIL

- [ ] T016 [P] [US2] Write unit tests in `tests/unit/observability/test_langfuse_client.py` covering: singleton `instance()` returns same object on repeated calls, `submit()` calls underlying Langfuse SDK trace/span creation, `flush()` calls SDK flush, `atexit` is registered exactly once at singleton creation (mock `atexit.register`), when SDK raises on submit a `WARNING` is logged and no exception propagates to caller, `is_connected()` returns `True` after successful init
- [ ] T017 [P] [US2] Write integration tests in `tests/integration/test_langfuse_client_integration.py` covering: real Langfuse connection established using credentials from ConfigManager, synthetic `TelemetryEvent` submitted and `flush()` called without error, singleton stable across multiple calls

### Implementation for User Story 2

- [ ] T018 [US2] Implement `TelemetryEvent` dataclass with fields `session_id: str`, `trace_id: str | None`, `name: str`, `input: dict | str | None`, `output: dict | str | None`, `metadata: dict`, `start_time: datetime | None`, `end_time: datetime | None` — in `deepeval/observability/langfuse_client.py`
- [ ] T019 [US2] Implement `LangfuseClient` Singleton: reads `LANGFUSE_HOST`, `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY` from `ConfigManager.instance()`; initializes `langfuse.Langfuse` client; registers `self.flush` via `atexit.register()` at singleton creation — in `deepeval/observability/langfuse_client.py`
- [ ] T020 [US2] Implement `LangfuseClient.submit(event: TelemetryEvent) -> None` that queues the event to the Langfuse SDK; catches any SDK exception, logs a `WARNING` with the error detail, and continues without re-raising (FR-007) — in `deepeval/observability/langfuse_client.py`
- [ ] T021 [US2] Implement `LangfuseClient.flush() -> None` calling `self._client.flush()` and `LangfuseClient.is_connected() -> bool` returning `True` when `_client` is initialized — in `deepeval/observability/langfuse_client.py`
- [ ] T022 [US2] Implement `LangfuseError` exception class in `deepeval/observability/langfuse_client.py`; export `LangfuseClient`, `TelemetryEvent`, `LangfuseError` from `deepeval/observability/__init__.py`

**Checkpoint**: `uv run pytest tests/unit/observability/ -v` must be GREEN. User Story 2 is independently testable.

---

## Phase 5: User Story 3 — Vector Store Access for Orchestration (Priority: P3)

**Goal**: `QdrantVectorStoreProvider` Singleton returns `langchain_qdrant.QdrantVectorStore` instances for named collections, auto-creating if absent, using a globally configured embedding model from `config/settings.yaml`.

**Independent Test**: `provider.get_store("test-coll")` returns a `QdrantVectorStore`; `add_documents()` and `similarity_search()` work; `as_retriever()` returns a `VectorStoreRetriever`; invalid collection name raises `VectorStoreError`; Qdrant unreachable raises `VectorStoreError`.

### Tests for User Story 3 — Write FIRST, verify RED before T025

> **RED**: Run `uv run pytest tests/unit/vector_store/ -v` after T023 — ALL tests must FAIL

- [ ] T023 [P] [US3] Write unit tests in `tests/unit/vector_store/test_qdrant_provider.py` covering: singleton `instance()` returns same object, `get_store()` with valid name succeeds, `get_store()` with invalid name (e.g. `"has spaces"`) raises `VectorStoreError`, collection name matching `^[a-zA-Z0-9_-]+$` is accepted, `collection_exists()` returns correct boolean, shared underlying `QdrantClient` is reused across multiple `get_store()` calls (mock to verify single init), Qdrant unreachable raises `VectorStoreError` with no credential exposure
- [ ] T024 [P] [US3] Write integration tests in `tests/integration/test_qdrant_provider_integration.py` covering: real Qdrant connection established, collection auto-created when absent, document added via `add_documents()` and retrieved via `similarity_search()`, `as_retriever()` returns usable `VectorStoreRetriever`, `delete_collection()` removes collection (teardown)

### Implementation for User Story 3

- [ ] T025 [US3] Implement `VectorCollection` dataclass with `name: str`, `embedding_model: str`, `embedding_dimensions: int`, `created_at: datetime | None`; implement `VectorStoreError` exception class — in `deepeval/vector_store/qdrant_provider.py`
- [ ] T026 [US3] Implement `QdrantVectorStoreProvider` Singleton: reads `QDRANT_HOST`, `QDRANT_PORT`, `QDRANT_API_KEY`, `embedding.model`, `embedding.dimensions` from `ConfigManager.instance()`; initializes shared `QdrantClient` and `OpenAIEmbeddings` with the global embedding model; raises `VectorStoreError` on connection failure without exposing credentials — in `deepeval/vector_store/qdrant_provider.py`
- [ ] T027 [US3] Implement `QdrantVectorStoreProvider.get_store(collection_name: str) -> QdrantVectorStore`: validates `collection_name` against `^[a-zA-Z0-9_-]+$` (raises `VectorStoreError`); auto-creates collection in Qdrant if absent using `langchain_qdrant.QdrantVectorStore`; caches provisioned collection names to avoid redundant checks; returns `QdrantVectorStore` instance natively compatible with LangChain/LangGraph (FR-009) — in `deepeval/vector_store/qdrant_provider.py`
- [ ] T028 [P] [US3] Implement `QdrantVectorStoreProvider.collection_exists(collection_name: str) -> bool` and `delete_collection(collection_name: str) -> None` (for test teardown) — in `deepeval/vector_store/qdrant_provider.py`
- [ ] T029 [US3] Export `QdrantVectorStoreProvider`, `VectorStoreError` from `deepeval/vector_store/__init__.py`

**Checkpoint**: `uv run pytest tests/unit/vector_store/ -v` must be GREEN. User Story 3 is independently testable.

---

## Phase 6: User Story 4 — Provider-Agnostic LLM Instantiation (Priority: P4)

**Goal**: `LLMProviderFactory.create(provider)` returns a ready-to-use `LLMProviderBase` instance (implementing `DeepEvalBaseLLM`) for OpenAI, Anthropic, or OpenRouter — all credentials sourced from `ConfigManager`, no arguments accepted.

**Independent Test**: `LLMProviderFactory.create("openai")` returns an `OpenAIProvider`; `provider.generate("Say PASS")` returns `(str, TokenUsage)`; `create("unsupported")` raises `LLMProviderError` naming the unsupported value and listing supported options; missing API key raises `LLMProviderError`.

### Tests for User Story 4 — Write FIRST, verify RED before T036

> **RED**: Run `uv run pytest tests/unit/llm/ -v` after T030–T034 — ALL tests must FAIL

- [ ] T030 [P] [US4] Write unit tests in `tests/unit/llm/test_llm_provider_base.py` covering: `LLMProviderBase` is ABC and cannot be instantiated directly, abstract properties `provider_name` and `model_name` are enforced on subclass, concrete `get_model_name()` delegates to `model_name`
- [ ] T031 [P] [US4] Write unit tests in `tests/unit/llm/test_openai_provider.py` covering: reads `OPENAI_API_KEY` and `OPENAI_DEFAULT_MODEL` from `ConfigManager` (not from constructor args), wraps `langchain_openai.ChatOpenAI` internally as `_lc_model`, `generate()` returns `(str, TokenUsage)`, `a_generate()` returns same types async, missing `OPENAI_API_KEY` raises `LLMProviderError`
- [ ] T032 [P] [US4] Write unit tests in `tests/unit/llm/test_anthropic_provider.py` covering: reads `ANTHROPIC_API_KEY` and `ANTHROPIC_DEFAULT_MODEL` from `ConfigManager`, wraps `langchain_anthropic.ChatAnthropic` as `_lc_model`, `generate()` and `a_generate()` return correct types, missing key raises `LLMProviderError`
- [ ] T033 [P] [US4] Write unit tests in `tests/unit/llm/test_openrouter_provider.py` covering: reads `OPENROUTER_API_KEY` and `OPENROUTER_DEFAULT_MODEL` from `ConfigManager`, wraps `langchain_openrouter.ChatOpenRouter` (NOT `ChatOpenAI`) as `_lc_model`, `generate()` and `a_generate()` return correct types
- [ ] T034 [P] [US4] Write unit tests in `tests/unit/llm/test_llm_factory.py` covering: `create("openai")` returns `OpenAIProvider` instance, `create("anthropic")` returns `AnthropicProvider`, `create("openrouter")` returns `OpenRouterProvider`, `create("unsupported")` raises `LLMProviderError` with message containing the unsupported value and listing all supported providers, optional `model=` argument overrides the ConfigManager default
- [ ] T035 [P] [US4] Write integration tests in `tests/integration/test_llm_factory_integration.py` covering: each configured provider executes a real completion via `generate()`, unsupported provider error message includes supported provider names

### Implementation for User Story 4

- [ ] T036 [US4] Implement `LLMProviderBase` ABC in `deepeval/llm/base.py` extending `DeepEvalBaseLLM` (from `deepeval.models`): declare `@abstractmethod` properties `provider_name: str` and `model_name: str`; declare `@abstractmethod` methods `generate(prompt: str) -> tuple[str, TokenUsage]` and `async a_generate(prompt: str) -> tuple[str, TokenUsage]`; implement concrete `get_model_name() -> str` delegating to `self.model_name`; declare `_lc_model: BaseChatModel` as expected internal attribute
- [ ] T037 [P] [US4] Implement `OpenAIProvider(LLMProviderBase)` in `deepeval/llm/openai_provider.py`: reads `OPENAI_API_KEY` and `OPENAI_DEFAULT_MODEL` from `ConfigManager.instance()` (raises `LLMProviderError` if missing); sets `_lc_model = ChatOpenAI(api_key=..., model=...)`; implements `generate()` and `a_generate()` via `_lc_model.invoke()` / `_lc_model.ainvoke()`
- [ ] T038 [P] [US4] Implement `AnthropicProvider(LLMProviderBase)` in `deepeval/llm/anthropic_provider.py`: reads `ANTHROPIC_API_KEY` and `ANTHROPIC_DEFAULT_MODEL` from `ConfigManager.instance()`; sets `_lc_model = ChatAnthropic(api_key=..., model=...)`; implements same interface as `OpenAIProvider`
- [ ] T039 [P] [US4] Implement `OpenRouterProvider(LLMProviderBase)` in `deepeval/llm/openrouter_provider.py`: reads `OPENROUTER_API_KEY` and `OPENROUTER_DEFAULT_MODEL` from `ConfigManager.instance()`; sets `_lc_model = ChatOpenRouter(openrouter_api_key=..., model=...)` from `langchain_openrouter` (NOT `ChatOpenAI`); implements same interface
- [ ] T040 [US4] Implement `LLMProviderFactory` in `deepeval/llm/factory.py`: define `_registry: ClassVar[dict[str, type[LLMProviderBase]]] = {"openai": OpenAIProvider, "anthropic": AnthropicProvider, "openrouter": OpenRouterProvider}`; implement `create(provider: str, model: str | None = None) -> LLMProviderBase` raising `LLMProviderError` for unsupported providers (error names the value and lists `_registry` keys); implement `supported_providers() -> tuple[str, ...]`
- [ ] T041 [US4] Export `LLMProviderBase`, `LLMProviderFactory`, `LLMProviderError` from `deepeval/llm/__init__.py`; implement `LLMProviderError` exception class in `deepeval/llm/base.py`

**Checkpoint**: `uv run pytest tests/unit/llm/ -v` must be GREEN. User Story 4 is independently testable.

---

## Phase 7: User Story 5 — Trace Extraction for Evaluation Input (Priority: P5)

**Goal**: `TraceRepository` reads traces from Langfuse SDK and returns structured `TraceRecord` instances; raw Langfuse API responses are never exposed.

**Independent Test**: `repo.get_by_session("sess-id")` returns `list[TraceRecord]` with all fields populated; `repo.get_by_session("nonexistent")` returns `[]` without error; Langfuse unavailable raises `TraceRepositoryError`.

### Tests for User Story 5 — Write FIRST, verify RED before T044

> **RED**: Run `uv run pytest tests/unit/repositories/test_trace_repository.py -v` after T042 — ALL tests must FAIL

- [ ] T042 [P] [US5] Write unit tests in `tests/unit/repositories/test_trace_repository.py` covering: `get_by_bot(bot_id)` returns `list[TraceRecord]` with all entity fields, `get_by_session(session_id)` returns matching traces, `get_by_date_range(bot_id, start, end)` filters by UTC timestamps, empty result returns `[]` without raising, raw Langfuse response objects are never returned (all results are `TraceRecord` instances), `output=None` is handled for interrupted sessions (edge case), Langfuse SDK raises → `TraceRepositoryError` is raised
- [ ] T043 [P] [US5] Write integration tests in `tests/integration/test_trace_repository_integration.py` covering: seeded trace (from Quickstart Scenario 2) retrieved by session ID, date range filter excludes out-of-range traces, nonexistent session returns `[]`, all fields of returned `TraceRecord` match the seeded data

### Implementation for User Story 5

- [ ] T044 [US5] Implement `TraceRecord` dataclass with fields `trace_id: str`, `session_id: str | None`, `bot_id: str`, `input: dict | str`, `output: dict | str | None`, `metadata: dict`, `start_time: datetime`, `end_time: datetime | None` — in `deepeval/repositories/models.py`
- [ ] T045 [US5] Implement `TraceRepository` class in `deepeval/repositories/trace_repository.py`: delegates SDK connection to `LangfuseClient.instance()`; implement `get_by_bot(bot_id: str) -> list[TraceRecord]`, `get_by_session(session_id: str) -> list[TraceRecord]`, `get_by_date_range(bot_id, start, end) -> list[TraceRecord]` using Langfuse SDK fetch/list API; all three return `[]` on empty result (no error)
- [ ] T046 [US5] Implement private `TraceRepository._to_trace_record(raw) -> TraceRecord` mapping raw Langfuse SDK trace object to `TraceRecord`; handle `output=None` for interrupted sessions; never expose raw SDK response to callers (FR-014); raise `TraceRepositoryError` wrapping any Langfuse SDK exception — in `deepeval/repositories/trace_repository.py`
- [ ] T047 [US5] Implement `TraceRepositoryError` exception class; export `TraceRepository`, `TraceRecord`, `TraceRepositoryError` from `deepeval/repositories/__init__.py`

**Checkpoint**: `uv run pytest tests/unit/repositories/test_trace_repository.py -v` must be GREEN. User Story 5 is independently testable.

---

## Phase 8: User Story 6 — Evaluation Results Persistence (Priority: P6)

**Goal**: `EvaluationRepository` persists `EvaluationResult` to Supabase with an application-generated UUID; `org_id` is always included in every insert even when `None`; write failures raise `RepositoryError`.

**Independent Test**: `repo.save(result)` returns `result.id` (the pre-generated UUID); `repo.get_by_id(id)` retrieves all fields including `org_id=None`; write failure raises `RepositoryError` (no silent data loss).

### Tests for User Story 6 — Write FIRST, verify RED before T050

> **RED**: Run `uv run pytest tests/unit/repositories/test_evaluation_repository.py -v` after T048 — ALL tests must FAIL

- [ ] T048 [P] [US6] Write unit tests in `tests/unit/repositories/test_evaluation_repository.py` covering: `save(result)` returns `result.id` UUID (the same one passed in), `org_id=None` is always included in the Supabase insert dict (never omitted), Supabase SDK raises on insert → `RepositoryError` raised (no silent data loss), `get_by_id(id)` returns matching `EvaluationResult` with all fields, `get_by_bot(bot_id)` returns filtered list, `get_by_bot(bot_id, date=...)` filters by UTC day
- [ ] T049 [P] [US6] Write integration tests in `tests/integration/test_evaluation_repository_integration.py` covering: real Supabase insert with application-generated UUID, all fields including `org_id=None` persisted correctly, `get_by_id()` retrieves exact record matching all fields, `get_by_bot()` returns results for correct bot only

### Implementation for User Story 6

- [ ] T050 [US6] Run the `evaluation_results` SQL schema from `data-model.md` in the Supabase SQL editor to create the table: `id UUID PRIMARY KEY`, `bot_id TEXT NOT NULL`, `trace_id TEXT`, `metric_name TEXT NOT NULL`, `score FLOAT NOT NULL`, `passed BOOLEAN NOT NULL`, `threshold FLOAT NOT NULL`, `reason TEXT`, `metadata JSONB DEFAULT '{}'`, `org_id UUID`, `created_at TIMESTAMPTZ NOT NULL`
- [ ] T051 [US6] Implement `EvaluationResult` dataclass with fields `id: UUID`, `bot_id: str`, `trace_id: str | None`, `metric_name: str`, `score: float`, `passed: bool`, `threshold: float`, `reason: str | None`, `metadata: dict`, `org_id: UUID | None`, `created_at: datetime` — in `deepeval/repositories/models.py`
- [ ] T052 [US6] Implement `EvaluationRepository` class in `deepeval/repositories/evaluation_repository.py`: reads `SUPABASE_URL` and `SUPABASE_SERVICE_KEY` from `ConfigManager.instance()`; initializes `supabase.create_client()`; implement `save(result: EvaluationResult) -> UUID` that inserts all fields to `evaluation_results` table including `org_id` (always, even if `None`) and returns `result.id`; raises `RepositoryError` on Supabase SDK exception
- [ ] T053 [US6] Implement `EvaluationRepository.get_by_id(result_id: UUID) -> EvaluationResult` and `get_by_bot(bot_id: str, date: datetime | None = None) -> list[EvaluationResult]` in `deepeval/repositories/evaluation_repository.py`; both raise `RepositoryError` on DB failure; `get_by_bot` returns `[]` when no records match
- [ ] T054 [US6] Implement `RepositoryError` exception class; export `EvaluationRepository`, `EvaluationResult`, `RepositoryError` from `deepeval/repositories/__init__.py`

**Checkpoint**: `uv run pytest tests/unit/repositories/test_evaluation_repository.py -v` must be GREEN. User Story 6 is independently testable.

---

## Phase 9: Polish & Cross-Cutting Concerns

**Purpose**: Quality gate verification and end-to-end validation.

- [ ] T055 [P] Run full unit test suite with coverage enforcement: `uv run pytest tests/unit/ --cov=deepeval --cov-report=term-missing --cov-fail-under=80 -v`; fix any module below 80% coverage before marking done (SC-003)
- [ ] T056 [P] Audit for hardcoded credentials: `grep -rE "(api_key|secret|password|token|host)\s*=\s*['\"][^'\"\$\{]" deepeval/`; result must be empty (SC-004 / constitution Principle IV)
- [ ] T057 Run Quickstart Scenarios 1–6 from `specs/001-m1-foundation-infrastructure/quickstart.md` in order to validate all six modules end-to-end against real services
- [ ] T058 Run the full round-trip scenario from `quickstart.md` (SC-005): read trace from Langfuse → create LLM judge → score → persist result to Supabase; confirm result appears in `evaluation_results` table

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **Foundational (Phase 2)**: Depends on Phase 1 — BLOCKS all user story test tasks (T008+)
- **User Stories (Phase 3–8)**: All depend on Phase 2 completion; US1 (P1) blocks all integration tests for other stories since all modules read from ConfigManager
- **Polish (Phase 9)**: Depends on all six user stories being complete

### User Story Dependencies

| Story | Priority | Dependency | Notes |
|-------|----------|-----------|-------|
| US1 — ConfigManager | P1 | Phase 2 only | Foundational; all modules depend on it |
| US2 — LangfuseClient | P2 | US1 (reads ConfigManager) | Unit tests mock ConfigManager |
| US3 — QdrantProvider | P3 | US1 (reads ConfigManager) | Unit tests mock ConfigManager |
| US4 — LLMProviderFactory | P4 | US1 (reads ConfigManager) | Unit tests mock ConfigManager |
| US5 — TraceRepository | P5 | US1 + US2 (uses LangfuseClient) | Unit tests mock both; integration tests need US2 done |
| US6 — EvaluationRepository | P6 | US1 (reads ConfigManager) | Independent of other stories |

### Within Each User Story

```
Tests (RED) → must FAIL before implementation starts
  ↓
Implementation (GREEN) → minimum code to make tests pass
  ↓
Refactor → clean up while keeping tests GREEN
  ↓
Checkpoint → run story's unit tests, confirm 100% pass
```

### Parallel Opportunities

After Phase 2:
- US1 must complete first (real implementation, not just mocking)
- After US1 is GREEN: US2, US3, US4, US6 can start in parallel (each mocks ConfigManager in unit tests)
- US5 can start its unit tests in parallel with the others; its integration tests need US2 complete

---

## Parallel Example: User Story 4 (US4 has the most parallelism)

```bash
# All six test files can be written in parallel (different files):
T030 → tests/unit/llm/test_llm_provider_base.py
T031 → tests/unit/llm/test_openai_provider.py
T032 → tests/unit/llm/test_anthropic_provider.py
T033 → tests/unit/llm/test_openrouter_provider.py
T034 → tests/unit/llm/test_llm_factory.py
T035 → tests/integration/test_llm_factory_integration.py

# Three provider implementations can proceed in parallel after T036 (base):
T037 → deepeval/llm/openai_provider.py
T038 → deepeval/llm/anthropic_provider.py
T039 → deepeval/llm/openrouter_provider.py
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (CRITICAL — blocks all tests)
3. Complete Phase 3: User Story 1 (ConfigManager)
4. **STOP and VALIDATE**: `uv run pytest tests/unit/config/ -v` + Quickstart Scenario 1
5. All other modules can now read configuration

### Incremental Delivery

1. Setup + Foundational → skeleton ready
2. US1 (P1) → ConfigManager GREEN → all modules can read config
3. US2 (P2) → LangfuseClient GREEN → telemetry online
4. US3 (P3) → QdrantProvider GREEN → vector store ready
5. US4 (P4) → LLMProviderFactory GREEN → LLM judges available
6. US5 (P5) → TraceRepository GREEN → trace reads available
7. US6 (P6) → EvaluationRepository GREEN → persistence complete
8. Phase 9: Polish → full round-trip verified (SC-005)

---

## Notes

- **[P]** = task creates/modifies a different file than other [P] tasks in the same phase
- **[Story]** label maps task to user story for independent traceability
- TDD is NON-NEGOTIABLE (constitution Principle III): every RED task must visibly fail before its GREEN tasks begin — this is verifiable in commit history
- Commit after each phase checkpoint so the RED→GREEN→REFACTOR cycle is visible in git log
- Never pass credentials as constructor arguments — all credentials come from `ConfigManager.instance()`
- Integration tests hit real services — ensure services are reachable before running them (see quickstart.md Prerequisites)

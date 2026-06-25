# Feature Specification: M1 — Foundation and Infrastructure

**Feature Branch**: `001-m1-foundation-infrastructure`

**Created**: 2026-06-23

**Status**: Draft

**Input**: User description: "Módulos em escopo para M1 — Fundação e Infraestrutura: ConfigManager (Singleton), LangfuseClient (Singleton), QdrantVectorStoreProvider (Provider/Factory), LLMProviderFactory (Factory Method), TraceRepository (Repository), EvaluationRepository (Repository)"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Secure Centralized Configuration (Priority: P1)

A developer building any module in the evaluation system needs to read a configuration value (an API key, a service host, a threshold). Instead of reaching for environment variables or YAML files directly, every module obtains all configuration through a single authoritative source. That source loads `.env` and `config/*.yaml` once at startup and makes values available on demand, ensuring no credentials can be accidentally logged or duplicated across modules.

**Why this priority**: Every other module in M1 depends on configuration values. If configuration access is fragmented — each module reading its own environment — secrets leak into logs, overrides become inconsistent, and testing becomes unreliable. This is the foundation the rest of M1 is built on.

**Independent Test**: Fully testable by verifying that calling the configuration accessor returns correct values loaded from `.env` and YAML, that a second call returns the same instance (no re-read), and that direct environment access from any other module is blocked by design.

**Acceptance Scenarios**:

1. **Given** a `.env` file and `config/settings.yaml` both present, **When** the configuration source is first accessed, **Then** all values from both files are available via a single accessor without any module importing environment libraries directly.
2. **Given** the configuration source already loaded, **When** a second module requests it, **Then** the exact same instance is returned with no re-read of files.
3. **Given** a missing required key in the configuration, **When** any module requests that key, **Then** an explicit, descriptive error is raised that names the missing key and its expected source file.
4. **Given** configuration values are loaded, **When** any value is logged or printed, **Then** sensitive keys (API keys, passwords, tokens) are masked and never appear in plain text in output.

---

### User Story 2 - Reliable Observability Telemetry (Priority: P2)

An operator running evaluations needs all evaluation runs and interactions to be automatically traced and exported to the self-hosted observability platform. The connection is established once at application start, reused throughout the session, and cleanly flushed on shutdown — so no telemetry is lost due to open buffers.

**Why this priority**: Langfuse is the primary data source for `TraceRepository` (P5). If telemetry is not reliably exported, the entire trace-based evaluation loop breaks. The connection lifecycle must be solid before trace reading can be meaningful.

**Independent Test**: Testable by starting the application, triggering a synthetic trace event, and confirming the event appears in the Langfuse UI. Shutdown flush is testable by verifying buffered events are present after a graceful stop.

**Acceptance Scenarios**:

1. **Given** valid Langfuse connection credentials in configuration, **When** the application starts, **Then** a single active connection to the observability platform is established and available system-wide.
2. **Given** an active connection, **When** a telemetry event is submitted, **Then** the event is queued for export and eventually appears in the observability platform without manual intervention.
3. **Given** the application is shutting down, **When** shutdown is triggered, **Then** all buffered telemetry events are flushed to the platform before the process exits.
4. **Given** the observability platform is temporarily unreachable, **When** events are submitted, **Then** the system continues operating without crashing; retry and back-off are handled by the observability SDK's built-in async flush mechanism, and a warning is logged to indicate the connectivity issue.

---

### User Story 3 - Vector Store Access for Orchestration (Priority: P3)

An evaluation workflow that uses RAG needs to store and retrieve vector embeddings through an interface that is natively compatible with the LangChain/LangGraph orchestration layer. The vector store is set up once (collections created if absent), and subsequent consumers receive ready-to-use store instances without knowing the underlying connection details.

**Why this priority**: RAG evaluation is a core evaluation type. Without a compatible vector store interface, RAG-based test cases cannot be executed. This module decouples the evaluation workflows from low-level vector database setup.

**Independent Test**: Testable by requesting a named vector store instance, writing a document, and confirming retrieval by semantic query returns the correct document — independently of any evaluation pipeline.

**Acceptance Scenarios**:

1. **Given** Qdrant connection parameters in configuration, **When** a named collection is requested, **Then** if the collection does not exist it is created automatically; if it exists, it is reused.
2. **Given** a provisioned collection, **When** a consumer requests a vector store instance for that collection, **Then** a fully initialised, query-ready store instance is returned.
3. **Given** multiple consumers requesting the same collection, **When** each requests an instance, **Then** the underlying connection is shared — not duplicated — and each consumer receives an equivalent, usable instance.
4. **Given** Qdrant is unreachable during startup, **When** a consumer requests a store instance, **Then** a clear error is raised that describes the connection failure without exposing credentials.

---

### User Story 4 - Provider-Agnostic LLM Instantiation (Priority: P4)

An evaluation pipeline needs a language model to score outputs. It declares which provider and model it wants (OpenAI, Anthropic, or OpenRouter) through configuration. The system returns a ready-to-use model instance through a unified interface — the pipeline never needs to know which SDK or credentials were used under the hood.

**Why this priority**: DeepEval metrics require an LLM judge. If each metric or pipeline hard-codes its provider, adding a new provider or switching between them requires code changes everywhere. The factory makes provider selection a configuration concern, not a code concern.

**Independent Test**: Testable by requesting each supported provider by name and confirming the returned instance can execute a simple completion — independently of any evaluation metric.

**Acceptance Scenarios**:

1. **Given** an OpenAI API key in configuration, **When** an OpenAI provider instance is requested with a valid model name, **Then** a ready-to-use LLM instance is returned that can execute completions.
2. **Given** an Anthropic API key in configuration, **When** an Anthropic provider instance is requested, **Then** a ready-to-use LLM instance is returned through the same interface as OpenAI.
3. **Given** OpenRouter credentials and a custom endpoint in configuration, **When** an OpenRouter provider instance is requested, **Then** a ready-to-use LLM instance is returned that routes through OpenRouter.
4. **Given** an unsupported provider name, **When** a provider instance is requested, **Then** a descriptive error is raised that names the unsupported provider and lists supported options.
5. **Given** a missing API key for a requested provider, **When** instantiation is attempted, **Then** a clear error is raised naming the missing credential and its expected configuration location.

---

### User Story 5 - Trace Extraction for Evaluation Input (Priority: P5)

An evaluation workflow needs to read bot interaction traces stored in Langfuse to use them as inputs for scoring. It queries by bot identifier, date range, or session — and receives structured trace records without knowing anything about the Langfuse API directly.

**Why this priority**: Traces are the primary input for evaluation. Without a clean read interface, every evaluation component would couple directly to the observability platform's API, making the system brittle to API changes.

**Independent Test**: Testable by seeding a known trace in Langfuse, querying it by session ID through the repository, and verifying the returned record matches the seeded data.

**Acceptance Scenarios**:

1. **Given** traces exist in Langfuse for a given bot identifier, **When** traces are queried by that identifier, **Then** all matching trace records are returned as structured objects with input, output, and metadata.
2. **Given** a date-range filter is applied, **When** traces are queried, **Then** only traces within that range are returned.
3. **Given** no traces match the query criteria, **When** traces are queried, **Then** an empty result set is returned without error.
4. **Given** the Langfuse connection is unavailable, **When** a trace query is attempted, **Then** a clear error is raised describing the connectivity failure.

---

### User Story 6 - Evaluation Results Persistence (Priority: P6)

After an evaluation run completes, all metrics, scores, and structured results need to be persisted to the relational database so they can be queried for reporting and trend analysis. The persistence layer accepts structured evaluation records and stores them reliably, independent of where results are also exported (e.g., Langfuse, CSV).

**Why this priority**: Persistent results are the foundation for dashboards and historical analysis. Without reliable persistence, every evaluation run is ephemeral and the system cannot support trend tracking or longitudinal reporting.

**Independent Test**: Testable by persisting a synthetic evaluation result record and immediately querying it back — confirming all fields including `org_id` are stored correctly.

**Acceptance Scenarios**:

1. **Given** a completed evaluation result with metric scores and metadata, **When** the result is persisted, **Then** all fields are written to the relational database and can be retrieved by result identifier.
2. **Given** a persisted result, **When** it is retrieved by bot identifier and date, **Then** the complete record including all metric scores is returned accurately.
3. **Given** a database write fails (e.g., connectivity issue), **When** a result is submitted for persistence, **Then** a clear error is raised and the calling workflow is notified — no silent data loss.
4. **Given** a new result record, **When** it is written, **Then** an `org_id` field is included in the stored record, even if null, to support future multi-tenant activation.

---

### Edge Cases

- A configuration key present in `.env` or `config/*.yaml` with an empty string value is treated identically to a missing key — `ConfigManager` raises an FR-003 descriptive error naming the key and its expected source file.
- What happens when both `.env` and `config/settings.yaml` define the same key with different values?
- What happens when the vector store collection name contains invalid characters?
- What happens when a Langfuse trace has no output (e.g., an interrupted session)?
- What happens when the database is available but the target table does not exist?
- What happens when an LLM provider returns an authentication error mid-evaluation?

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST provide a single, authoritative source for all configuration values loaded from `.env` and `config/*.yaml` files; no other module may read these files or environment variables directly.
- **FR-002**: The configuration source MUST load all values exactly once per process; subsequent requests MUST return the same values without re-reading files.
- **FR-003**: The configuration source MUST raise a descriptive error — naming the key and expected source — when a required key is absent or has an empty string value; an empty string is treated identically to a missing key.
- **FR-004**: The configuration source MUST mask sensitive values (keys, tokens, passwords) in any logging or string representation.
- **FR-005**: The system MUST maintain a single active connection to the self-hosted observability platform per process; all telemetry consumers MUST share this connection.
- **FR-006**: The observability connection MUST flush all buffered telemetry events before process shutdown completes.
- **FR-007**: The system MUST continue operating when the observability platform is temporarily unreachable, logging a warning without crashing; retry and back-off behaviour are delegated entirely to the observability SDK's built-in async flush mechanism — no custom retry layer is implemented.
- **FR-008**: The system MUST expose vector store instances for named collections through a unified interface; collections MUST be created automatically if they do not exist. The embedding model and its dimensions MUST be sourced from `config/settings.yaml` via `ConfigManager` — a single global model applies to all collections in V1.
- **FR-009**: The vector store interface MUST be natively compatible with the LangChain/LangGraph orchestration layer so evaluation workflows can use it without adaptation.
- **FR-010**: The system MUST support instantiation of LLM provider instances for OpenAI, Anthropic, and OpenRouter through a single, unified interface.
- **FR-011**: LLM provider instantiation MUST source all credentials and endpoint configuration from the configuration source; no credentials may be passed as direct arguments.
- **FR-012**: The system MUST raise a descriptive error when an unsupported provider name is requested, listing supported options.
- **FR-013**: The trace read interface MUST support querying traces by bot identifier, date range, and session identifier.
- **FR-014**: The trace read interface MUST return structured objects with input, output, and metadata; raw API responses MUST NOT be exposed to callers.
- **FR-015**: The evaluation persistence layer MUST write metric scores, evaluation results, and associated metadata to the relational database. Each result MUST be assigned a UUID primary key generated by the application (via `uuid.uuid4()`) before the database insert, so the identifier is known to the caller without waiting for a database response.
- **FR-016**: Every record written by the evaluation persistence layer MUST include an `org_id` field (nullable) to support future multi-tenant activation.
- **FR-017**: The evaluation persistence layer MUST raise a clear error on write failure; silent data loss is not permitted.

### Key Entities

- **ConfigEntry**: A named configuration value with its source file, key name, and sensitivity classification (sensitive/non-sensitive).
- **TelemetryEvent**: A trace or span event submitted to the observability platform, with a session identifier, timestamps, input, output, and metadata.
- **VectorCollection**: A named collection in the vector store containing embedded documents, identified by collection name and embedding dimensions. Embedding dimensions are derived from a single global embedding model configured in `config/settings.yaml`; all collections in V1 use the same model.
- **LLMProviderInstance**: A ready-to-use language model handle identified by provider name and model name, capable of executing completions.
- **TraceRecord**: A structured representation of a single bot interaction trace, containing session ID, bot identifier, turn inputs/outputs, timestamps, and metadata.
- **EvaluationResult**: A persisted evaluation record containing a UUID primary key (generated by the application before insert), bot identifier, trace reference, metric name, score, pass/fail status, metadata, and `org_id`.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: All six foundation modules are operational and their acceptance scenarios pass with zero manual intervention after configuration files are populated.
- **SC-002**: Any new module added to the project can obtain configuration, a vector store instance, or an LLM instance without importing any configuration library or provider SDK directly — verified by dependency audit.
- **SC-003**: All foundation modules have ≥ 80% test coverage as reported by the coverage tool, with tests written before production code (TDD cycle verifiable in commit history).
- **SC-004**: Zero hardcoded credentials appear in any source file — verified by grep on all new and changed files.
- **SC-005**: A complete evaluation round-trip (read trace → run evaluation → persist result) completes successfully in a local environment without requiring code changes beyond configuration file population.
- **SC-006**: Adding a new LLM provider in a future milestone requires only a new subclass — zero changes to existing factory or consumer code — confirmed by a spike demonstrating extensibility.
- **SC-007**: Telemetry events submitted during an evaluation run are visible in the Langfuse observability platform within 30 seconds of submission under normal operating conditions.

## Assumptions

- All external services (Langfuse, Qdrant, Supabase) are reachable from the development environment via the credentials supplied in `.env`.
- The Langfuse instance is self-hosted on the VPS and already running; this milestone does not cover Langfuse server provisioning.
- The Qdrant instance is self-hosted on the VPS and already running; this milestone does not cover Qdrant server provisioning.
- The Supabase project is already created and the target schema (evaluation results table) will be created as part of this milestone. `EvaluationRepository` (V1) connects via the Supabase Python SDK (`supabase>=2.0.0`) using its table/insert/select API; the Repository pattern isolates all SDK calls within the repository so a future V2 swap to self-hosted Postgres requires changes only to `EvaluationRepository`.
- Python `^3.11` is the minimum runtime version; `^3.13` is the pinned version for local development via `uv`.
- OpenRouter is accessed via the OpenAI SDK using a custom `base_url`; no separate OpenRouter SDK is required.
- Multi-tenancy is out of scope for M1; `org_id` is included as a nullable column to avoid a future schema migration, not to enforce tenant isolation.
- Configuration merging priority (if a key appears in both `.env` and YAML): `.env` takes precedence over YAML — this is the standard dotenv convention.
- The `config/` directory structure (`settings.yaml`, `bots.yaml`, `personas.yaml`) exists or will be created as part of this milestone.
- Mobile or web-facing interfaces are out of scope for M1; this milestone is back-end infrastructure only.

## Clarifications

### Session 2026-06-25

- Q: When a required configuration key exists but has an empty string value, should `ConfigManager` treat it as missing (raise FR-003 error) or as a valid empty string? → A: Empty string treated as missing — raise FR-003 error (same path as absent key).
- Q: When Langfuse is unreachable, should `LangfuseClient` implement custom retry logic, buffer events indefinitely, discard immediately, or delegate to the SDK? → A: Delegate entirely to the Langfuse SDK's built-in async flush/retry mechanism — no custom retry layer.
- Q: How should the embedding model for `QdrantVectorStoreProvider` be configured — global default, per-collection, or caller-provided? → A: Single global default in `config/settings.yaml`; all V1 collections use the same model and dimensions.
- Q: What primary key strategy should `EvaluationResult` use — application-generated UUID, Supabase auto-UUID, or auto-increment? → A: Application-generated UUID (`uuid.uuid4()`) before insert; ID is known to the caller without a DB round-trip.
- Q: Should `EvaluationRepository` (V1) use the Supabase Python SDK, a raw PostgreSQL driver, or SQLAlchemy? → A: Supabase Python SDK (`supabase>=2.0.0`) for V1; Repository pattern isolates the SDK so V2 Postgres swap touches only the repository.

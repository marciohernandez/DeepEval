# Tasks: Synthetic Dataset Generator (M4.1)

**Input**: Design documents from `/specs/008-synthetic-dataset-generator/`

**Prerequisites**: constitution v1.4.0, plan.md, spec.md, research.md, data-model.md,
contracts/synthetic-dataset-api.md, quickstart.md

**Tests**: Mandatory under Constitution Principle IV. Every test task below includes running the
focused test and observing the intended RED failure before its dependent production task starts.
Unit tests and automated integration tests are both required; manual checks do not satisfy a gate.

**Organization**: Tasks are grouped by user story. Setup and foundational tasks establish shared
configuration, schema, persona, and authentication boundaries.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel because it touches different files and has no incomplete dependency.
- **[Story]**: Maps a task to US1, US2, or US3.
- Every task names an exact file path.

---

## Phase 1: Setup and Governed Infrastructure

**Purpose**: Install constitution-approved dependencies and establish configuration/schema through
RED-before-GREEN tasks.

- [x] T000 Record the mandatory LangChain MCP consultation in `specs/008-synthetic-dataset-generator/research.md`, including native invocation/integration alternatives considered and the selected API; this blocked T001-T047 and could not be replaced by the earlier official-web-documentation check — completed 2026-07-15 via the `claude.ai Langchain 1.0` MCP server, recorded in research.md R6
- [X] T001 Write and run failing configuration contract tests in `tests/unit/config/test_synthetic_config.py` proving `config/settings.yaml` contains all `synthetic.*` settings/exporter class paths, `.env.example` contains only the new credential `SUPABASE_ANON_KEY=`, and no `SYNTHETIC_*` environment keys exist
- [X] T002 [P] Add constitution-approved `pypdf`, `docx2txt`, and `chromadb` dependencies to `pyproject.toml` and update `uv.lock` with `uv add pypdf docx2txt chromadb`
- [X] T003 Update `config/settings.yaml` with `synthetic.docs_dir`, `synthetic.output_dir`, `synthetic.goldens_per_persona`, `synthetic.conversations_per_persona`, `synthetic.max_conversation_turns`, and JSON/CSV exporter dotted paths; add empty `SUPABASE_ANON_KEY=` to `.env.example`; run T001 GREEN
- [X] T004 [P] Write and run failing migration contract tests in `tests/unit/repositories/test_synthetic_migration.py` asserting all three tables, nullable `org_id` on every table, child org-inheritance guards, indexes, RLS enablement, and JWT-org policies from data-model.md
- [X] T005 Create `migrations/002_synthetic_datasets.sql` exactly from data-model.md, including three tables, child org inheritance/mismatch rejection, indexes, and RLS policies; run T004 GREEN
- [X] T006 [P] Create empty package initializers `deepeval_platform/synthetic/__init__.py` and `tests/unit/synthetic/__init__.py`

**Checkpoint**: Approved dependencies, non-secret settings, credential example, package skeleton, and
schema contract are ready.

---

## Phase 2: Foundational Persona and Authentication Boundaries

**Purpose**: Shared persona resolution and authenticated organization context required by every
story.

**CRITICAL**: No user-story implementation starts until this phase is GREEN.

- [X] T007 [P] Write and run failing tests in `tests/unit/synthetic/test_persona_config_resolver.py` for `Persona`/`PersonaScenario`, all configured styling fields, nested scenario parsing, zero personas, explicit empty selection, selected persona filtering, and a selected-but-missing persona error
- [X] T008 Implement `Persona` and `PersonaScenario` dataclasses in `deepeval_platform/synthetic/persona.py`; run their T007 cases GREEN
- [X] T009 Implement `PersonaConfigError` and `PersonaConfigResolver.resolve(persona_names: list[str] | None)` in `deepeval_platform/synthetic/persona_config_resolver.py`, reading only through `ConfigManager`; run all T007 cases GREEN
- [X] T010 Populate `config/personas.yaml` with the data-model examples only after T007 is RED; verify T007 remains GREEN against controlled config fixtures
- [X] T011 [P] Write and run failing tests in `tests/unit/synthetic/test_authorization.py` for valid JWT principal resolution, expired/invalid tokens, missing/malformed `app_metadata.org_id`, user-scoped Supabase client creation with `SUPABASE_ANON_KEY`, token secrecy in logs/repr, and absence of caller-provided org override
- [X] T012 Implement `AuthenticatedPrincipal`, `AuthorizationError`, and `OrganizationAuthorizer` in `deepeval_platform/synthetic/authorization.py`; validate Supabase Auth, derive organization only from trusted claims, create a JWT-scoped client, and run T011 GREEN

**Checkpoint**: Requested personas resolve deterministically and every public flow can obtain a
trusted principal without accepting arbitrary `org_id`.

---

## Phase 3: User Story 1 - Generate Exact Persona-Styled Goldens (Priority: P1) MVP

**Goal**: Generate the exact configured count per selected persona while covering every valid
document, isolating parser failures, and retaining structured failure/persona metadata.

**Independent Test**: Use real PDF/Markdown/DOCX fixtures with one persona and a stubbed LLM seam;
verify exact count, one or more goldens per valid document, forwarded styling fields, persona
association, and structured handling of one corrupted document.

### Tests for User Story 1

- [X] T013 [US1] Write and run failing unit tests in `tests/unit/synthetic/test_golden_generator.py` for empty knowledge base, target below valid-document count, stable per-document `divmod` allocation, one native call per document, exact truncation, underproduction error without partial return, all styling fields forwarded, persona association, and structured readability/parsing `DocumentFailure` values
- [X] T014 [US1] Write real PDF/Markdown/DOCX plus corrupt fixtures and run the failing integration suite in `tests/integration/test_synthetic_document_loaders_integration.py`, exercising DeepEval's native loader path while stubbing only the LLM/generation seam downstream of parsing

### Implementation for User Story 1

- [X] T015 [US1] Implement `EmptyKnowledgeBaseError`, `InsufficientGoldenCoverageError`, and `GoldenGenerator` in `deepeval_platform/synthetic/golden_generator.py`: validate/load each document independently through the native path, distribute the exact target by `divmod`, generate per document, sanitize structured failures, truncate deterministic overproduction, reject underproduction, and preserve persona/source associations; run T013 and T014 GREEN

**Checkpoint**: US1 is independently usable and satisfies FR-001 through FR-004, FR-013, FR-014,
SC-001, and SC-003.

---

## Phase 4: User Story 2 - Generate Normalized Live-Bot Conversations (Priority: P2)

**Goal**: Invoke Flowise or LangChain/LangGraph through extensible configured subclasses and emit
the same normalized conversation/status contract.

**Independent Test**: Run one persona/scenario against a local HTTP bot and equivalent direct-call
fixture; verify normalized ordered turns and each ending state.

### Tests for User Story 2

- [X] T016 [P] [US2] Write and run failing ABC tests in `tests/unit/synthetic/test_bot_invoker_base.py` for the `BotInvokerBase.__call__(input, turns, thread_id) -> Turn` contract and non-instantiability
- [X] T017 [P] [US2] Write and run failing tests in `tests/unit/synthetic/test_flowise_bot_invoker.py` for payload/session ID, non-empty JSON `text` extraction, non-2xx/I/O/malformed responses, sanitized structured `[BOT_UNREACHABLE]` metadata, and never-raise behavior
- [X] T018 [P] [US2] Write and run failing tests in `tests/unit/synthetic/test_langchain_bot_invoker.py` for native `.invoke()` plus `str`, `BaseMessage.content`, dict `output`/`text`/`answer` normalization and structured failures for resolution, invocation, empty, or malformed results
- [X] T019 [P] [US2] Write and run failing tests in `tests/unit/synthetic/test_bot_invoker_factory.py` proving configured dotted subclasses load, non-subclasses/abstract/missing targets fail clearly, and a custom test subclass works using configuration only with no factory registry edit
- [X] T020 [P] [US2] Write and run failing tests in `tests/unit/synthetic/test_conversation_generator.py` for stable scenario `divmod`, configured max turns, expected-outcome completion, natural conclusion, max-turn incomplete fallback, bot-failure precedence, transcript retention, normalized persona/scenario fields, and continuation of every remaining persona/scenario attempt after one bot callback fails
- [X] T021 [US2] Write and run the failing local-server integration suite in `tests/integration/test_flowise_bot_invoker_integration.py`, verifying a real HTTP request/response, session propagation, and malformed/non-2xx normalization without external credentials

### Implementation for User Story 2

- [X] T022 [US2] Implement `BotInvokerBase` in `deepeval_platform/synthetic/bot_invoker_base.py`; run T016 GREEN
- [X] T023 [P] [US2] Implement `FlowiseBotInvoker` in `deepeval_platform/synthetic/flowise_bot_invoker.py` with normalized response extraction and sanitized marker turns; depends on T022 and runs T017/T021 GREEN
- [X] T024 [P] [US2] Implement `LangChainBotInvoker` in `deepeval_platform/synthetic/langchain_bot_invoker.py` using native `.invoke()` and normalized result extraction; depends on T022 and runs T018 GREEN
- [X] T025 [US2] Implement config-driven dotted-class `BotInvokerFactory` in `deepeval_platform/synthetic/bot_invoker_factory.py` with no platform registry; depends on T022-T024 and runs T019 GREEN
- [X] T026 [US2] Add `invocation.invoker_class` and invoker-specific options to `config/bots.yaml` only after T019 is RED, then implement `ConversationGenerator` in `deepeval_platform/synthetic/conversation_generator.py` using native `ConversationSimulator`, completion callback/metadata extraction, stable distribution, and ending-status precedence; depends on T020/T025 and runs T020 GREEN

**Checkpoint**: US2 satisfies FR-005 through FR-008, FR-015, FR-017, FR-020, SC-002, and SC-007.

---

## Phase 5: User Story 3 - Authenticated Persistence, Search, and Export (Priority: P3)

**Goal**: Persist and retrieve complete datasets through RLS, search goldens and conversations,
recover failed indexing, and export through extensible strategies.

**Independent Test**: With two authenticated test organizations, generate and persist a dataset,
reload it in a fresh service, search both content types, export JSON/CSV, and prove cross-org denial.

### Tests for User Story 3

- [X] T027 [P] [US3] Write and run failing repository/model tests in `tests/unit/repositories/test_dataset_repository.py` for aggregate row mapping, structured document failures, persisted/reloaded conversation `bot_error`, distinct run IDs, principal-only method signatures, same-org filtering, both content types in `synthetic_content`, normalized `SearchResult`, failed-index cleanup/exclusion, whole-dataset retry, and no export methods on the repository
- [X] T028 [P] [US3] Write and run failing exporter tests in `tests/unit/synthetic/test_dataset_exporters.py` proving JSON/CSV include metadata, goldens, conversations, ending/bot errors, and document failures without leaking access tokens
- [X] T029 [P] [US3] Write and run failing factory tests in `tests/unit/synthetic/test_dataset_exporter_factory.py` for configured dotted subclasses, invalid targets, supported JSON/CSV, and a custom exporter loaded solely through config
- [X] T030 [US3] Write and run failing facade tests in `tests/unit/synthetic/test_synthetic_dataset_generator.py` for authentication before every public method, selected personas, settings resolution through `ConfigManager`, generator composition, non-persistence on golden coverage failure, distinct runs, retrieval/list/search/retry, and authenticated export delegation
- [X] T031 [US3] Write and run the failing environment-backed integration suite in `tests/integration/test_synthetic_storage_integration.py` for Supabase Auth/RLS same-org access, cross-org denial, child org inheritance/mismatch rejection, Qdrant indexing of both content types, failure cleanup, and retry; include a controlled semantic corpus where a known relevant golden and conversation result each rank within the first three for their query (SC-005); mark with `integration` and skip explicitly when dedicated service variables are absent
- [X] T032 [US3] Write and run the failing primary-flow integration suite in `tests/integration/test_synthetic_generation_flow_integration.py` for authenticated generation -> persistence -> fresh-service retrieval -> semantic search -> JSON/CSV export using a stubbed LLM, a local Flowise HTTP bot, a local LangChain direct-call bot, and test Supabase/Qdrant; run generation against both bot invokers side by side and assert their resulting conversation records share identical normalized fields and status semantics (SC-007); inject one failed conversation attempt and prove all remaining persona/scenario attempts complete while the failed transcript and structured `bot_error` survive fresh retrieval and both exports

### Implementation for User Story 3

- [X] T033 [US3] Add `DocumentFailure`, `SyntheticDataset`, `GoldenRecord`, `ConversationRecord`, `ConversationEndingStatus`, and `SearchResult` models to `deepeval_platform/repositories/models.py`; run model portions of T027 GREEN
- [X] T034 [US3] Implement persistence-only `DatasetRepository` in `deepeval_platform/repositories/dataset_repository.py` using `AuthenticatedPrincipal.supabase_client`, application org filters plus RLS, aggregate save/load/list, atomic-visibility indexing of goldens and conversations in `synthetic_content`, normalized search, cleanup on failure, and whole-dataset retry; depends on T033 and runs T027/T031 repository cases GREEN
- [X] T035 [US3] Implement `DatasetExporterBase` in `deepeval_platform/synthetic/dataset_exporter_base.py`; run base-class cases from T028 GREEN
- [X] T036 [P] [US3] Implement `JsonDatasetExporter` in `deepeval_platform/synthetic/json_dataset_exporter.py`; depends on T035 and runs JSON cases from T028 GREEN
- [X] T037 [P] [US3] Implement `CsvDatasetExporter` in `deepeval_platform/synthetic/csv_dataset_exporter.py`; depends on T035 and runs CSV cases from T028 GREEN
- [X] T038 [US3] Implement config-driven dotted-class `DatasetExporterFactory` in `deepeval_platform/synthetic/dataset_exporter_factory.py`; depends on T035-T037 and runs T029 GREEN
- [X] T039 [P] [US3] Export repository models and `DatasetRepository` from `deepeval_platform/repositories/__init__.py`; depends on T033-T034
- [X] T040 [US3] Implement authenticated `SyntheticDatasetGenerator` facade in `deepeval_platform/synthetic/synthetic_dataset_generator.py` with `generate`, `get_dataset`, `list_datasets`, `search_content`, `retry_indexing`, and `export_dataset`; authorize first, use `synthetic.*` settings, compose generators/repository/exporters, and never expose raw `org_id`; depends on T009/T012/T015/T026/T034/T038 and runs T030-T032 GREEN

**Checkpoint**: US3 satisfies FR-009 through FR-012, FR-016, FR-018, FR-019, FR-021, and SC-004
through SC-006 plus SC-008.

---

## Phase 6: Quality Gates and Regression Validation

- [X] T041 Run `uv run pytest tests/unit/synthetic tests/unit/repositories/test_dataset_repository.py tests/unit/repositories/test_synthetic_migration.py tests/unit/config/test_synthetic_config.py -v` and resolve failures without weakening assertions
- [X] T042 Run all four automated integration files from quickstart.md with `-m integration`; record any environment skips as unresolved gates rather than replacing them with manual checks
- [X] T043 Run `uv run pytest --cov=deepeval_platform --cov-report=term-missing --cov-fail-under=80` and add RED-first tests for uncovered branches in every new/changed module before implementation changes
- [X] T044 Run `uv run pytest` to verify zero regressions across existing M1-M3 behavior
- [X] T045 Verify configuration/security gates: no `SYNTHETIC_*` environment keys, no hardcoded credentials, no access-token logging, no public raw-`org_id` operation, every table has nullable `org_id`, and RLS integration assertions are GREEN
- [X] T046 Execute every quickstart.md automated command and confirm its requirement-to-test matrix is GREEN, including both semantic content types and both export formats
- [X] T047 Re-check and record the DeepEval-first and LangChain-first evidence in `specs/008-synthetic-dataset-generator/research.md` and the final gate status in `specs/008-synthetic-dataset-generator/plan.md`; fail completion if the native-framework decisions or mandatory MCP evidence are absent

---

## Dependencies and Execution Order

### Phase Dependencies

- Setup requires constitution v1.4.0 to be present before T002.
- T000 was a constitution gate blocking T001-T047 until a LangChain MCP
  server was available and the consultation result recorded in research.md;
  this is now resolved (see research.md R6).
- Foundational depends on Setup and blocks all user stories.
- US1 and US2 may proceed in parallel after Foundational.
- US3 depends on US1 and US2 because its facade composes both generators.
- Quality gates depend on every selected story being complete.

### Strict TDD Dependencies

- T003 depends on T001 RED; T005 depends on T004 RED.
- T008-T010 depend on T007 RED; T012 depends on T011 RED.
- T015 depends on T013 and T014 RED.
- T022-T026 depend on T016-T021 RED as specified per task.
- T033-T040 depend on T027-T032 RED as specified per task.
- A test file merely existing is insufficient: its focused command must fail for the intended
  missing behavior before production work starts.

### Parallel Opportunities

- T001, T002, T004, and T006 touch independent files.
- T007 and T011 are independent foundational test cycles.
- US1 and US2 can run concurrently after Phase 2.
- T016-T020 are independent unit-test files; T023/T024 are parallel after T022.
- T027-T029 are independent US3 test files; T036/T037 are parallel after T035.

---

## Implementation Strategy

### MVP First

1. Complete governed Setup and Foundational phases.
2. Complete US1 through T015.
3. Run T013/T014 and the relevant coverage command.
4. Stop with an independently usable exact, document-covered golden generator.

### Incremental Delivery

1. US1 delivers exact single-turn datasets with structured document failures.
2. US2 adds normalized live-bot conversations without changing existing factories.
3. US3 composes both behind authenticated persistence, search, retry, and export.
4. Phase 6 proves constitutional gates and regression safety.

## Notes

- New bot and export types require only a subclass plus configuration; fixed registries are forbidden.
- `DatasetRepository` has no export-format responsibility.
- Search indexes both goldens and conversations, never partial failed-index content.
- Credentials remain in `.env`; synthetic settings remain in `config/settings.yaml`.
- Do not commit after each task automatically; commits are created only when explicitly requested.

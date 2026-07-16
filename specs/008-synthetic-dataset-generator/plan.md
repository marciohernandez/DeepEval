# Implementation Plan: Synthetic Dataset Generator

**Branch**: `008-synthetic-dataset-generator` | **Date**: 2026-07-15 | **Spec**: [spec.md](./spec.md)

## Summary

M4.1 adds `deepeval_platform/synthetic/` around a `SyntheticDatasetGenerator` facade. Single-turn
generation uses DeepEval `Synthesizer` and its native PDF/Markdown/DOCX loader path. Each readable
document is generated separately for failure isolation and coverage. The configured total is exact:
after native loader validation, `divmod` assigns at least one golden to every valid document;
native overproduction is deterministically truncated and underproduction raises
`InsufficientGoldenCoverageError`. Parser/unreadable failures become persisted `DocumentFailure`
records and are included in exports.

Multi-turn generation uses `ConversationSimulator`. `BotInvokerFactory` imports the configured
`bots.<id>.invocation.invoker_class` and validates that it is a `BotInvokerBase` subclass; there is
no platform registry. Flowise and LangChain invokers normalize their supported response forms to a
`Turn`, and malformed/I/O responses return a structured `[BOT_UNREACHABLE]` turn. Completion status
is captured from `on_simulation_complete` and native test-case metadata where available, with an
explicit fallback based on bot failure and max-turn exhaustion.

All public generate, retrieve, list, semantic-search, retry-indexing, and export operations require
an `access_token`. `OrganizationAuthorizer` validates the Supabase Auth JWT, derives `org_id` only
from trusted `app_metadata`, and creates a user-scoped Supabase client carrying the JWT. Repository
operations accept the resulting `AuthenticatedPrincipal`, never a caller-provided organization ID,
so Supabase RLS and application filtering both apply. All three tables have nullable `org_id`; child
rows copy the parent value and migration policies enforce organization membership.

Goldens and conversations are indexed in one Qdrant `synthetic_content` collection. Search returns
normalized `SearchResult` values. Indexing is all-or-nothing at dataset visibility: any failed write
deletes all points for that dataset, marks it failed, excludes it from search, and can be retried.
Export is separate from persistence: `DatasetExporterFactory` imports
`synthetic.exporters.<format>` dotted classes, validates `DatasetExporterBase`, and the facade loads
the authorized dataset before delegating.

## Technical Context

**Language/Version**: Python 3.13 in this repository; constitution minimum Python `^3.11`.

**Primary Dependencies**:
- Existing `deepeval ^4.0.6`: `Synthesizer`, `StylingConfig`, `ConversationSimulator`,
  `ConversationalGolden`, `ConversationalTestCase`, and `Turn`.
- New `pypdf`, `docx2txt`, and `chromadb`, explicitly approved by constitution v1.4.0. They support
  DeepEval's native loaders/context construction and are not treated as amendment exemptions.
- Existing `supabase>=2.0.0` for Auth, user-scoped PostgREST access, and RLS.
- Existing `QdrantVectorStoreProvider` for the `synthetic_content` collection.
- Existing `ConfigManager`, the only reader of YAML and `.env` values.

**Configuration**:
- `config/settings.yaml`: `synthetic.docs_dir`, `synthetic.output_dir`,
  `synthetic.goldens_per_persona`, `synthetic.conversations_per_persona`,
  `synthetic.max_conversation_turns`, and `synthetic.exporters.<format>`.
- `config/personas.yaml`: personas and scenarios.
- `config/bots.yaml`: each generated-against bot has `invocation.invoker_class`; Flowise also has
  `endpoint_url`, while LangChain has `chain_target`.
- `.env`: credentials only. The planned `.env.example` update adds `SUPABASE_ANON_KEY=` for
  authenticated, user-scoped Supabase access. Synthetic paths and thresholds are not env vars.

**Storage**:
- Supabase tables `synthetic_datasets`, `synthetic_goldens`, `synthetic_conversations`, created by
  `migrations/002_synthetic_datasets.sql` with RLS enabled.
- Qdrant collection `synthetic_content`, containing both record types with `content_type`,
  `source_record_id`, `dataset_id`, `org_id`, `persona_name`, and type-specific metadata.
- JSON/CSV files beneath configured `synthetic.output_dir`; these are not the system of record.

**Testing**: Strict TDD. For every behavior, write the test and run it to observe RED before writing
production code, then implement GREEN and refactor while green. Unit tests mock LLM, Supabase,
Qdrant, and bot boundaries. Automated integration tests cover real PDF/MD/DOCX parsing without a
real LLM, a local HTTP Flowise server, environment-skippable Supabase/Qdrant services, and the full
generation -> persistence -> retrieval path. Manual checks do not satisfy the integration gate.

**Constraints**:
- `goldens_per_persona` must be at least the number of readable, parser-valid documents.
- Every valid document contributes at least one golden and the persona total is exact.
- Every configured `StylingConfig` field is forwarded; each output retains its persona association.
- All public paths authenticate before data access; no caller-controlled `org_id` path exists.
- New bot type or exporter requires only a subclass plus configuration.

**Scale/Scope**: 1 new domain package; 14 behavior classes (`PersonaConfigResolver`, two generators,
four bot-invocation classes, four exporter classes, `OrganizationAuthorizer`, the facade, and
`DatasetRepository`); 8 principal/config/persistence/result models; focused error types; 1 migration
with 3 tables and RLS policies; 3 approved dependencies; 1 credential example key; coordinated
settings/persona/bot configuration updates. Counts exclude exceptions and DeepEval/native models.

## Constitution Check

*GATE: Re-checked against constitution v1.4.0.*

| Principle | Check | Status |
|---|---|---|
| I. OOP-First | Generation, authorization, invocation, export, and persistence have separate responsibilities and polymorphic extension points. | PASS |
| II. DeepEval-First | Official DeepEval Synthesizer documentation and installed `4.0.7` signatures were consulted and recorded in research.md R2; native `Synthesizer`, loaders, styling, and `ConversationSimulator` are used. | PASS |
| III. LangChain-First | The mandatory LangChain MCP consultation was completed via the `claude.ai Langchain 1.0` MCP server and recorded in research.md R6; it confirms native `.invoke()` returning `AIMessage.content`. | PASS |
| IV. TDD | Tests are run and observed RED before production code; unit and real automated integration suites are required; coverage remains >=80%. | PASS (process gate) |
| V. Zero Hardcode | Settings are under `config/settings.yaml`, bot/persona details under their YAML files, credentials only in `.env`, all read via `ConfigManager`. | PASS |
| VI. Extensibility | Dotted-class factories require subclass + config only; repository is not responsible for export formatting. | PASS |
| Approved stack | `pypdf`, `docx2txt`, and `chromadb` are explicitly approved by constitution v1.4.0. | PASS |

No design-pattern exception is requested. Constitution v1.4.0 is in force. All principle checks
pass; no implementation blocker remains.

## Final Gate Status (Phase 6, T041-T047, 2026-07-16)

All 47 tasks (T001-T047) are complete. Full detail, including exact commands and pass/fail/skip
counts, is recorded in research.md "Post-implementation gate status". Summary:

| Principle/Gate | Status | Evidence |
|---|---|---|
| I. OOP-First | PASS | 14 single-responsibility classes across `synthetic/` and `repositories/`; ABCs (`BotInvokerBase`, `DatasetExporterBase`) enforce polymorphic extension. |
| II. DeepEval-First | PASS | Native `Synthesizer`, `StylingConfig`, `ConversationSimulator`, `ConversationalGolden`, `Turn` used throughout; no reimplementation of DeepEval scoring/generation logic. |
| III. LangChain-First | PASS | `LangChainBotInvoker` uses native `.invoke()`/`BaseMessage.content` per the MCP-verified contract in research.md R6; document loaders are the native `langchain_community` classes. |
| IV. TDD | PASS | Every task's test file was written and observed RED before its production module; T041 focused suite 156/156 green; T043 coverage 100% on every new/changed module (97.94% project-wide, gate >=80%). |
| V. Zero Hardcode | PASS | `test_synthetic_config.py` proves no `SYNTHETIC_*` env keys exist and `.env.example` carries only `SUPABASE_ANON_KEY=`; grep for hardcoded credentials in `synthetic/` and `dataset_repository.py` is empty (T045). |
| VI. Extensibility | PASS | `BotInvokerFactory`/`DatasetExporterFactory` are dotted-class, registry-free; a custom test subclass loaded solely from config in both factories' test suites with zero factory edits. |
| Org-id readiness & migration compliance | PASS | `migrations/002_synthetic_datasets.sql` versioned; all 3 tables nullable `org_id`; child-row inheritance trigger rejects mismatches; RLS `SELECT`/`INSERT`/`UPDATE` policies with `WITH CHECK` (26/26 green in `test_synthetic_migration.py`). |
| Authentication and RLS | PASS (unit) / **UNRESOLVED (integration)** | Every public facade/repository method authenticates first and accepts no caller-supplied `org_id` (verified by signature introspection, T045). Live Supabase Auth/RLS same-org/cross-org/child-inheritance behavior is NOT verified end-to-end in this environment — `test_synthetic_storage_integration.py` and `test_synthetic_generation_flow_integration.py` (8 tests total) skip explicitly for missing `DATASET_TEST_ORG_A_ACCESS_TOKEN`/`DATASET_TEST_ORG_B_ACCESS_TOKEN`. This is recorded as an open gap requiring a dedicated Supabase/Qdrant test environment, not silently accepted as passing. |
| Regression safety | PASS | T044 full-suite run: 699 passed, 8 skipped (the gap above), 7 pre-existing failures unrelated to M4.1 (confirmed via `git stash` to fail identically before this feature; they require live Anthropic/OpenRouter/Supabase/Qdrant credentials absent from this sandbox). |

**Completion caveat**: this feature is functionally complete and all automatable gates pass, but the
Supabase Auth/RLS and full-flow integration suites have never executed against real infrastructure.
Before production sign-off, provision the dedicated test environment (`SUPABASE_URL`,
`SUPABASE_ANON_KEY`, two test users with distinct `app_metadata.org_id`,
`migrations/002_synthetic_datasets.sql` applied, real Qdrant) and re-run
`test_synthetic_storage_integration.py` and `test_synthetic_generation_flow_integration.py` with
`-m integration`.

## Project Structure

```text
deepeval_platform/
├── synthetic/
│   ├── persona.py
│   ├── persona_config_resolver.py
│   ├── authorization.py                 # principal, authorizer, authorization error
│   ├── golden_generator.py
│   ├── conversation_generator.py
│   ├── bot_invoker_base.py
│   ├── flowise_bot_invoker.py
│   ├── langchain_bot_invoker.py
│   ├── bot_invoker_factory.py
│   ├── dataset_exporter_base.py
│   ├── json_dataset_exporter.py
│   ├── csv_dataset_exporter.py
│   ├── dataset_exporter_factory.py
│   └── synthetic_dataset_generator.py
├── repositories/
│   ├── models.py                        # dataset records, DocumentFailure, SearchResult
│   └── dataset_repository.py
config/
├── settings.yaml                        # synthetic settings and exporter dotted classes
├── personas.yaml
└── bots.yaml                            # invoker dotted classes and invoker-specific options
migrations/
└── 002_synthetic_datasets.sql           # 3 tables, nullable org_id, triggers/checks, RLS
tests/
├── unit/config/test_synthetic_config.py
├── unit/synthetic/
├── unit/repositories/
│   ├── test_dataset_repository.py
│   └── test_synthetic_migration.py
└── integration/
    ├── test_synthetic_document_loaders_integration.py
    ├── test_flowise_bot_invoker_integration.py
    ├── test_synthetic_storage_integration.py
    └── test_synthetic_generation_flow_integration.py
```

`DatasetRepository` remains in the existing persistence package. Export strategies and the facade
remain in the synthetic domain because formatting and public workflow orchestration are not storage
queries.

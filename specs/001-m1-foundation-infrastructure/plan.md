# Implementation Plan: M1 — Foundation and Infrastructure

**Branch**: `001-m1-foundation-infrastructure` | **Date**: 2026-06-25 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/001-m1-foundation-infrastructure/spec.md`

## Summary

Build six foundation modules — ConfigManager, LangfuseClient, QdrantVectorStoreProvider,
LLMProviderFactory, TraceRepository, EvaluationRepository — that form the infrastructure
all future evaluation workflows depend on. Every module is implemented TDD-first (RED→GREEN→REFACTOR)
using LangChain-native integrations wherever they exist, with all credentials centralised in
ConfigManager and zero hardcoded values.

## Technical Context

**Language/Version**: Python 3.13 (pinned via `.python-version`); minimum `^3.11`

**Primary Dependencies**:
- `python-dotenv ^1.0.0` — ConfigManager: .env loading
- `PyYAML ^6.0` — ConfigManager: YAML loading
- `langfuse ^4.9.1` — LangfuseClient + TraceRepository
- `langchain-qdrant` — QdrantVectorStoreProvider (LangChain-first, Principle II)
- `langchain-openai` — OpenAIProvider + OpenAIEmbeddings
- `langchain-anthropic` — AnthropicProvider
- `langchain-openrouter ^0.2` — OpenRouterProvider (dedicated integration, not base_url workaround; verified on PyPI at 0.2.4, requires `langchain-core>=1.4.7` — compatible with `langchain ^1.x`)
- `supabase ^2.0.0` — EvaluationRepository
- `deepeval ^4.0.6` — DeepEvalBaseLLM interface for LLMProviderBase
- `pytest ^8.0.0`, `pytest-cov ^5.0.0`, `pytest-asyncio ^0.23.0`, `pytest-mock ^3.14.0`

**Storage**:
- Qdrant (vector, self-hosted VPS) — via `langchain_qdrant.QdrantVectorStore`
- Supabase Postgres (relational, cloud) — via `supabase>=2.0.0` SDK

**Testing**: pytest + pytest-cov (≥ 80% coverage) + pytest-asyncio + pytest-mock

**Target Platform**: Linux server (VPS self-hosted services); local dev on Linux/macOS

**Project Type**: Python backend library / service (infrastructure modules)

**Performance Goals**: No specific latency targets for M1 foundation. Singleton pattern
ensures no repeated I/O on config/connection setup.

**Constraints**:
- Zero hardcoded credentials (Principle IV)
- Single Singleton instance per process for ConfigManager, LangfuseClient, QdrantVectorStoreProvider
- LangChain-first: native integrations used for Qdrant, OpenAI, Anthropic, OpenRouter (Principle II)
- Tests written before production code (Principle III)
- DeepEvalBaseLLM interface required for all LLM providers (FR-010)

**Scale/Scope**: Single-tenant V1; 6 foundation modules; `org_id` nullable in all DB records

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design.*

| Gate | Pre-design Status | Post-design Status |
|------|------------------|--------------------|
| 1. TDD compliance | PLANNED — tasks.md will encode RED→GREEN→REFACTOR order | CONFIRMED — tasks.md encodes RED→GREEN→REFACTOR order throughout all phases; test tasks precede implementation tasks in every phase |
| 2. Coverage ≥ 80% | PLANNED — enforced via pytest-cov --cov-fail-under=80 | CONFIRMED — enforced via T004 `[tool.pytest.ini_options]` addopts and T055 full-suite gate |
| 3. Zero hardcode | PASS — all credentials in .env via ConfigManager; none in source | PASS |
| 4. Pattern compliance | PASS — Singleton, Factory Method, Repository applied correctly per constitution | PASS |
| 5. LangChain-first | PASS — MCP consulted; QdrantVectorStore, ChatOpenAI, ChatAnthropic, ChatOpenRouter all used | PASS |
| 6. Config completeness | PLANNED — .env.example to be created in implementation; ConfigManager sole reader | CONFIRMED — T006 creates `.env.example` with all 14 M1 keys; T059 enforces ConfigManager-only imports |
| 7. Org-id readiness | PASS — EvaluationResult has nullable org_id; always included in inserts | PASS |

**Gate 5 detail** (LangChain MCP findings):
- `langchain_qdrant.QdrantVectorStore` exists → MUST use for vector store (replacing raw qdrant-client)
- `langchain_openai.ChatOpenAI` exists → MUST use internally in OpenAIProvider
- `langchain_anthropic.ChatAnthropic` exists → MUST use internally in AnthropicProvider
- `langchain_openrouter.ChatOpenRouter` exists → MUST use for OpenRouter (NOT `ChatOpenAI + base_url`)
  - LangChain docs explicitly warn: "For OpenRouter, prefer the dedicated integration `ChatOpenRouter`"
  - Package verified on PyPI: `langchain-openrouter 0.2.4` (latest), requires `langchain-core>=1.4.7,<2.0.0`
  - The `^1.x` constitution constraint applies to core `langchain`/`langgraph` packages only; integration packages (`langchain-openrouter`, etc.) follow their own versioning — `0.2.x` is stable and LangChain-core-compatible
- `langchain_openai.OpenAIEmbeddings` exists → MUST use for Qdrant embedding model

**No gate violations.** No complexity tracking required.

## Project Structure

### Documentation (this feature)

```text
specs/001-m1-foundation-infrastructure/
├── plan.md              # This file
├── research.md          # Phase 0: LangChain MCP findings, dependency decisions
├── data-model.md        # Phase 1: Entity definitions, DB schema, relationships
├── quickstart.md        # Phase 1: End-to-end validation scenarios
├── contracts/           # Phase 1: Public Python interface specifications
│   ├── config_manager.py
│   ├── langfuse_client.py
│   ├── qdrant_provider.py
│   ├── llm_provider.py
│   └── repositories.py
└── tasks.md             # Phase 2 output (/speckit-tasks command)
```

### Source Code (repository root)

```text
deepeval/                          # Main package
├── __init__.py
├── config/
│   ├── __init__.py
│   └── config_manager.py          # ConfigManager (Singleton) + ConfigError
├── observability/
│   ├── __init__.py
│   └── langfuse_client.py         # LangfuseClient (Singleton) + TelemetryEvent
├── vector_store/
│   ├── __init__.py
│   └── qdrant_provider.py         # QdrantVectorStoreProvider (Singleton) + VectorStoreError
├── llm/
│   ├── __init__.py
│   ├── base.py                    # LLMProviderBase (ABC, implements DeepEvalBaseLLM)
│   ├── openai_provider.py         # OpenAIProvider (wraps ChatOpenAI)
│   ├── anthropic_provider.py      # AnthropicProvider (wraps ChatAnthropic)
│   ├── openrouter_provider.py     # OpenRouterProvider (wraps ChatOpenRouter)
│   └── factory.py                 # LLMProviderFactory (Factory Method)
└── repositories/
    ├── __init__.py
    ├── models.py                  # TraceRecord, EvaluationResult dataclasses
    ├── trace_repository.py        # TraceRepository (reads from Langfuse SDK)
    └── evaluation_repository.py   # EvaluationRepository (writes to Supabase)

config/                            # Non-sensitive config (versioned)
├── settings.yaml                  # embedding.model, embedding.dimensions, etc.
├── bots.yaml                      # Bot config (stub for M1)
└── personas.yaml                  # Personas (stub for M1)

migrations/                        # Versioned SQL migrations (committed, never manual)
└── 001_evaluation_results.sql     # DDL for evaluation_results table (Supabase/Postgres)

tests/
├── conftest.py                    # Shared fixtures: mock ConfigManager, mock env
├── unit/
│   ├── config/
│   │   └── test_config_manager.py
│   ├── observability/
│   │   └── test_langfuse_client.py
│   ├── vector_store/
│   │   └── test_qdrant_provider.py
│   ├── llm/
│   │   ├── test_llm_provider_base.py
│   │   ├── test_openai_provider.py
│   │   ├── test_anthropic_provider.py
│   │   ├── test_openrouter_provider.py
│   │   └── test_llm_factory.py
│   └── repositories/
│       ├── test_trace_repository.py
│       └── test_evaluation_repository.py
└── integration/
    ├── test_config_manager_integration.py
    ├── test_langfuse_client_integration.py
    ├── test_qdrant_provider_integration.py
    ├── test_llm_factory_integration.py
    ├── test_trace_repository_integration.py
    └── test_evaluation_repository_integration.py

.env.example                       # All required keys, no values (must be updated each new key)
```

**Structure Decision**: Single-project layout (`Option 1`). M1 is backend infrastructure only;
no frontend or API layer. All modules under the `deepeval/` package. Integration tests use
real services (no mocks) per the project's "never mock the database" stance.

## Complexity Tracking

No gate violations. No complexity justification required.

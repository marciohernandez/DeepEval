<!--
SYNC IMPACT REPORT
==================
Version change: (unversioned template) → 1.0.0 → 1.0.1
Bump type: MINOR (initial population) + PATCH (LangChain/LangGraph V1+ constraint made explicit)

Added sections:
  - Core Principles I–V (OOP-First, LangChain-First, TDD, Zero Hardcode, Extensibility by Design)
  - Technology Stack (binding V1 stack + multi-tenant strategy)
  - Quality Gates (7 gates + success criteria from briefing §7)
  - Governance (amendment procedure, versioning policy, compliance review)

Modified principles: N/A — initial constitution creation
Removed sections: N/A

Templates reviewed:
  ✅ .specify/templates/plan-template.md — "Constitution Check" is a runtime placeholder filled
     by /speckit-plan; no structural changes required. Quality Gates section provides the gate
     definitions that /speckit-plan must reference.
  ✅ .specify/templates/spec-template.md — Generic structure fully compatible with constitution
     scope; no changes required.
  ⚠  .specify/templates/tasks-template.md — Template marks tests as "OPTIONAL - only if
     explicitly requested." Principle III (TDD — NON-NEGOTIABLE) overrides this. Feature specs
     for this project MUST always enable test tasks. Recommend annotating the template or
     enforcing via /speckit-tasks prompt.
  N/A — No commands/ directory found under .specify/templates/; no command files to review.

Follow-up TODOs:
  - TODO(TASKS_TEMPLATE): Update tasks-template.md note to reflect that TDD is NON-NEGOTIABLE
    for this project; tests are never optional here.
  - Ratification date 2026-06-19 derived from briefing.md document date; confirm with Marcio.
-->

# DeepEval Chatbot Evaluator Constitution

## Core Principles

### I. Object-Oriented Architecture (OOP-First)

Every module MUST follow the OOP paradigm applying Encapsulation (protected internals, clear
interfaces), Inheritance (reuse without duplication), and Polymorphism (extensible without
breaking existing behaviour). Each class MUST have a single, well-defined responsibility — no
monolithic files. Modules MUST be organized by domain: evaluation, collection, persistence,
dashboard. High cohesion and low coupling are non-negotiable architectural constraints, not
aspirational targets.

**Rationale**: A growing fleet of bots with configurable metrics requires a structure that
absorbs new bots, new metrics, and new providers without touching working code. Strict
single-responsibility is the contract that makes that possible.

### II. LangChain-First Development

Before writing any code, the LangChain MCP MUST be consulted to verify whether a native class,
function, or integration already satisfies the requirement.

- If one exists → it MUST be used as-is, without adaptation or substitution by another framework.
- Only when no native option exists MAY code be developed from scratch or use another framework or libery.

This rule covers: chains, retrievers, callbacks, loaders, splitters, memory, agents, tools,
output parsers, and any other LangChain/LangGraph component.

**Version constraint (NON-NEGOTIABLE)**: LangChain MUST be `^1.x` and LangGraph MUST be `^1.x`.
The legacy 0.x API is incompatible with this project's architecture and MUST NOT be used under
any circumstance — not in dependencies, not in examples, not in adapters.

**Rationale**: LangChain/LangGraph is the orchestration layer for the bots being evaluated.
Native integrations ensure maximum compatibility with trace structures, callbacks, and the
Langfuse integration — avoiding unnecessary adapter code that could diverge from upstream.

### III. Test-Driven Development (TDD — NON-NEGOTIABLE)

Tests MUST be written before production code, without exception. The required cycle is:

1. Write the test → it MUST fail (RED)
2. Write the minimum code to make it pass (GREEN)
3. Refactor while keeping tests passing (GREEN)

- Framework: `pytest`
- Minimum coverage: ≥ 80% (enforced by `pytest-cov`)
- Scope: unit tests per class/module + integration tests for all primary flows
- Async tests: `pytest-asyncio`; isolation mocks: `pytest-mock`

**Rationale**: The evaluation system is itself a quality gate for production chatbots. It MUST
be held to the highest quality standard — regressions in the evaluator directly undermine trust
in every bot score it produces.

### IV. Zero Hardcode / Configuration Security

No credential, API key, token, password, or environment-specific value MAY appear in source
code. Without exception.

| Configuration type | Location |
|--------------------|----------|
| API keys, passwords, tokens | `.env` (never committed) |
| Environment settings (hosts, ports, thresholds) | `config/settings.yaml` |
| Bot configuration (metrics, schedule) | `config/bots.yaml` |
| Personas for synthetic datasets | `config/personas.yaml` |
| Production secrets | `.env.production` (never committed) |

Rules:
- `.env` and `.env.*` MUST always be listed in `.gitignore`.
- `.env.example` MUST always exist with all keys present but no values.
- Logs and console output MUST NEVER expose sensitive variable values.
- `ConfigManager` (Singleton) MUST be the sole point of configuration reading in the system.
  No other module may read `.env` or YAML files directly.

**Rationale**: This system holds API keys to LLM providers, Supabase, Qdrant, and Langfuse.
Credentials in source code are the most common catastrophic security failure — zero tolerance.

### V. Extensibility by Design (Design Patterns — Mandatory)

Adding a new bot type, metric, LLM provider, or export target MUST require only a new subclass.
Zero changes to existing working code are permitted for extension scenarios.

The following patterns MUST be applied in the specified contexts:

| Pattern | Mandatory application |
|---------|----------------------|
| **Factory Method** | `MetricFactory.create(name)` — instantiates DeepEval metrics without if/else chains;<br>`LLMProviderFactory.create(provider, model)` — instantiates the correct LLM provider |
| **Singleton** | `ConfigManager`, `LangfuseClient`, `QdrantClient` — one instance per process, no re-reads |
| **Strategy** | `TraceExtractor` — `FlowiseExtractor` and `LangChainExtractor` as interchangeable strategies;<br>new bot type = new subclass only |
| **Observer** | `ResultPublisher` — notifies Langfuse, CSV export, Qdrant, and Dashboard after evaluation;<br>new output target = new observer only |
| **Repository** | `TraceRepository`, `EvaluationRepository` — isolates storage queries from business logic;<br>DB backend swap (Supabase → Postgres) touches only repositories |

**Rationale**: The system is explicitly designed to grow: new bots, metrics, personas, providers.
Pattern enforcement is the mechanism that keeps growth from accumulating refactoring debt.

## Technology Stack

The approved V1 technology stack is binding. Substitutions or additions MUST be proposed as
constitution amendments (MINOR version bump minimum).

**Core runtime**: Python `^3.11`, managed with `uv`

**Evaluation framework**: DeepEval `^4.0.6` — all metrics, Synthesizer, ConversationSimulator,
PromptOptimizer (GEPA / MIPROv2)

**Observability**: Langfuse Python SDK `^4.9.1` (server: self-hosted on VPS)
- Flowise bots: traces arrive automatically via native Langfuse integration (read-only)
- LangChain/LangGraph bots: `langfuse.callback.CallbackHandler` for controlled trace structure

**Bot orchestration** (systems under evaluation): LangChain `^1.3.10`, LangGraph `^1.2.6`,
Flowise (self-hosted)
> ⚠ **Hard constraint**: LangChain MUST be `^1.x` (`^1.3.10` minimum) and LangGraph MUST be
> `^1.x` (`^1.2.6` minimum). The 0.x API MUST NOT be used — it is incompatible with the V1
> architecture and the LangChain-First principle (Principle II).

**Persistence**:
- Relational V1: Supabase cloud (Postgres + Auth + RLS) via `supabase>=2.0.0`
- Relational V2+: PostgreSQL self-hosted on VPS (swapped via Repository pattern + `DB_PROVIDER`)
- Vector: Qdrant `^1.18.0` client (server: self-hosted on VPS, API key required)

**LLM Providers**: OpenAI `>=1.30.0`, Anthropic `>=0.30.0`, OpenRouter via `langchain-openrouter`
(`ChatOpenRouter`) — all accessed through `LLMProviderBase` / `LLMProviderFactory`. The
`ChatOpenAI + base_url` workaround for OpenRouter MUST NOT be used; the dedicated LangChain
integration is required (Principle II).

**Backend API**: FastAPI `^0.115.0` + Uvicorn

**Frontend**: Next.js `^14.0`, shadcn/ui (CLI-installed), Tailwind CSS `^3.4`, Recharts `^2.12`,
TanStack Table `^8` — dark theme inspired by Confident AI

**Scheduling**: APScheduler `^3.10.0` with cron expressions per bot

**Configuration**: python-dotenv `^1.0.0`, PyYAML `^6.0`

**Testing**: pytest `^8.0.0`, pytest-cov `^5.0.0`, pytest-asyncio `^0.23.0`,
pytest-mock `^3.14.0`

**Containerization**: Docker + Docker Compose (app + Langfuse + Qdrant for local dev)

**Multi-tenant strategy**: V1 is single-tenant (one organisation). Every database table MUST
include an `org_id` nullable column from day one to enable V2 multi-tenant activation without
schema migration. `user_id` MUST NEVER be used as a global-scope identifier.

## Quality Gates

Every feature MUST pass all applicable gates before being considered complete:

1. **TDD compliance** — Tests were written before production code; RED→GREEN→REFACTOR cycle
   is evident in commit history.
2. **Coverage** — `pytest-cov` reports ≥ 80% for all new and changed modules.
3. **Zero hardcode** — Grep for hardcoded credentials returns empty on all new/changed files.
4. **Pattern compliance** — New bots, metrics, and providers added as subclasses only;
   no changes to existing factory, strategy, observer, or repository implementations.
5. **LangChain-first check** — Any LangChain-adjacent code is accompanied by a note confirming
   the LangChain MCP was consulted before writing the implementation.
6. **Config completeness** — `.env.example` is updated for every new environment variable
   introduced; `ConfigManager` is the only reader.
7. **Org-id readiness & migration compliance** (persistence tasks) — Every new database table
   includes `org_id` as a nullable column. Every database schema change MUST be committed as a
   versioned SQL migration file in `migrations/` (e.g., `001_evaluation_results.sql`); no schema
   may be applied via manual editor operations — manual steps are untrackable, unreproducible in
   CI, and violate the TDD commit-history requirement of Gate 1.

**Success criteria** (from briefing §7):
- Any bot declared in `bots.yaml` evaluates without additional code
- All DeepEval metrics can be activated per bot via configuration
- Evaluation covers single-turn, RAG, agents/tools, and multi-turn conversations
- Synthetic datasets generated from company documents and defined personas
- System supports new bots, metrics, and personas without refactoring
- Coverage ≥ 80% maintained via TDD

## Governance

This constitution supersedes all other development guidelines for the DeepEval Chatbot Evaluator
project. In case of conflict between this document and any other practice or guideline, the
constitution wins.

**Amendment procedure**:
1. Propose the change with written rationale (PR description or design note).
2. Run `/speckit-constitution` to produce the updated constitution with Sync Impact Report.
3. Propagate changes to affected templates and agent context files.
4. Increment version:
   - MAJOR: principle removal or redefinition incompatible with existing work
   - MINOR: new principle or section added, or materially expanded guidance
   - PATCH: clarifications, wording fixes, non-semantic refinements

**Compliance review**: Every PR MUST verify compliance with Principles I–V and the Quality
Gates section. Complexity deviations MUST be justified in the PR description with explicit
reference to the violated principle and why no simpler path exists.

**Runtime guidance**: See `CLAUDE.md` for agent-specific runtime instructions.

**Version**: 1.0.1 | **Ratified**: 2026-06-19 | **Last Amended**: 2026-06-22

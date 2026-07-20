<!--
SYNC IMPACT REPORT
==================
 Version change: 2.0.0 -> 2.1.0
 Bump type: MINOR (Technology Stack substitution requires MINOR minimum per Governance §Technology
 Stack; combined with a Gate 1 evidence-definition clarification that alone would be PATCH)

Triggered by: /speckit-analyze findings C1 and C2 on feature 009-evaluator-principal
 (research.md T056, T057), remediated per user request.

Added sections: N/A

Modified sections:
  - Technology Stack / Core runtime: `Python ^3.11` -> `Python ^3.13`, to match the actual binding
    constraint already in force in `pyproject.toml` (`>=3.13`, since commit e8deaa6, 2026-06-22)
    and `.python-version` (`3.13`). The prior `^3.11` floor was aspirational and unsatisfiable:
    `uv sync --python 3.11` is refused by `uv` under the current `pyproject.toml`, and the full
    test suite has only ever been verified GREEN on Python 3.13.13.
  - Quality Gates / Gate 1 (TDD compliance): evidence requirement widened from "evident in commit
    history" (only) to accept either fine-grained commit history OR, for phase/feature-granularity
    commit workflows, a documented per-task RED/GREEN audit note (as produced in
    specs/009-evaluator-principal/research.md T057). The substantive TDD requirement (tests before
    code, RED before GREEN, Principle IV) is unchanged — only what counts as acceptable *evidence*
    of compliance was relaxed.
  - Quality Gates / Gate 8: "TDD commit-history requirement of Gate 1" reworded to "TDD evidence
    requirement of Gate 1" for consistency with the Gate 1 change above.

Removed sections: N/A

Templates reviewed:
  - OK: .specify/templates/plan-template.md (generic placeholder example, e.g. "Python 3.11,
    Swift 5.9" — not a reference to this project's binding version; no change needed)
  - OK: .specify/templates/spec-template.md (no version or Gate 1 references)
  - OK: .specify/templates/tasks-template.md (no version or Gate 1 references)
  - OK: .specify/templates/commands/ (directory does not exist)
  - Updated: CLAUDE.md (Project section: "minimum runtime `^3.11` per constitution" -> `^3.13`)
  - Updated: tech_stack.md (§ Python row + changelog entry: `^3.11` (mínimo) -> `^3.13`)
  - Not updated (intentional): specs/*/plan.md and specs/*/spec.md across features 001-009, and
    specs/009-evaluator-principal/research.md — these are point-in-time milestone artifacts that
    recorded the constitution's `^3.11` statement as it stood *at the time each was written*.
    Rewriting them would misrepresent project history; research.md's T056 finding is precisely the
    audit trail that motivated this amendment and must stay as originally recorded.

Follow-up TODOs: N/A
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

### II. DeepEval-First Development

DeepEval is this project's **primary framework**. Before writing any code in the evaluation
domain — metrics, evaluation strategies, trace extraction/collection abstractions, synthetic
dataset generation (`Synthesizer`, `ConversationSimulator`), or prompt optimization
(`PromptOptimizer`) — the DeepEval library and its documentation MUST be consulted to verify
whether a native class, function, or abstraction already satisfies the requirement.

- If one exists → it MUST be used as-is, without reimplementation or substitution.
- Only when DeepEval offers no native equivalent MAY custom code be developed. This is expected
  for this project's own integration abstractions (e.g. `TraceExtractor`, `EvaluationStrategy`,
  `StrategyFactory`) — these exist specifically to adapt DeepEval's test-case/metric model to
  Flowise and LangChain/LangGraph bot traces, and MUST still follow Principle I (OOP) and
  Principle VI (Design Patterns).

This rule covers: all DeepEval metrics (`AnswerRelevancyMetric`, `FaithfulnessMetric`,
`ContextualPrecisionMetric`, `ToolCorrectnessMetric`, `ConversationCompletenessMetric`, etc.),
`LLMTestCase` / `ConversationalTestCase` / `MLLMTestCase`, `EvaluationDataset`, `Synthesizer`,
`ConversationSimulator`, `PromptOptimizer` (GEPA / MIPROv2), and `DeepEvalBaseLLM`.

**Rationale**: DeepEval is the evaluation engine that gives this system its purpose — every
metric, dataset, and optimization capability the project needs is either already implemented
natively or explicitly designed to be extended (via `DeepEvalBaseLLM`, custom `GEval` criteria,
etc.). Reimplementing what DeepEval already provides duplicates maintenance burden and risks
diverging from upstream scoring semantics that Confident AI dashboards and integrations expect.

### III. LangChain-First Development (Bot Orchestration Layer)

Before writing any code that orchestrates or integrates with a **bot under evaluation**, the
LangChain MCP MUST be consulted to verify whether a native class, function, or integration
already satisfies the requirement.

- If one exists → it MUST be used as-is, without adaptation or substitution by another framework.
- Only when no native option exists MAY code be developed from scratch or use another framework
  or library.

This rule covers: chains, retrievers, callbacks, loaders, splitters, memory, agents, tools,
output parsers, and any other LangChain/LangGraph component used to connect to, instrument, or
control a bot being evaluated (e.g. `langfuse.callback.CallbackHandler` wiring,
`langchain_qdrant.QdrantVectorStore` for vector storage integrations).

**Scope boundary (explicit)**: This principle does **NOT** apply to this system's own
evaluation-domain modules — `TraceExtractor`, `EvaluationStrategy`, `StrategyFactory`,
`MetricFactory`, or any other class whose responsibility is evaluating bots rather than being
one. Those modules are governed by Principle II (DeepEval-First). LangChain is the
orchestration layer for the bots being *evaluated*; it is not a candidate framework for the
evaluator's own architecture.

**Version constraint (NON-NEGOTIABLE)**: LangChain MUST be `^1.x` and LangGraph MUST be `^1.x`.
The legacy 0.x API is incompatible with this project's architecture and MUST NOT be used under
any circumstance — not in dependencies, not in examples, not in adapters.

**Rationale**: LangChain/LangGraph is the orchestration layer for the bots being evaluated —
secondary to DeepEval but still binding within its own scope. Native integrations ensure
maximum compatibility with trace structures, callbacks, and the Langfuse integration — avoiding
unnecessary adapter code that could diverge from upstream.

### IV. Test-Driven Development (TDD — NON-NEGOTIABLE)

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

### V. Zero Hardcode / Configuration Security

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

### VI. Extensibility by Design (Design Patterns — Mandatory)

Adding a new bot type, metric, LLM provider, or export target MUST require only a new subclass.
Zero changes to existing working code are permitted for extension scenarios.

The following patterns MUST be applied in the specified contexts:

| Pattern | Mandatory application |
|---------|----------------------|
| **Factory Method** | `MetricFactory.create(name)` — instantiates DeepEval metrics without if/else chains;<br>`LLMProviderFactory.create(provider, model)` — instantiates the correct LLM provider |
| **Singleton** | `ConfigManager`, `LangfuseClient`, `QdrantVectorStoreProvider` — one instance per process, no re-reads |
| **Strategy** | `TraceExtractor` — `FlowiseExtractor` and `LangChainExtractor` as interchangeable strategies;<br>new bot type = new subclass only |
| **Observer** | `ResultPublisher` — provides the extensible publication contract for evaluation results. A feature that introduces Langfuse, CSV export, Qdrant, Dashboard, or another output target MUST implement that target as a `ResultObserver`; a result-producing feature MAY implement the publisher contract without concrete destination observers when those destinations are explicitly out of scope.<br>new output target = new observer only, with zero `Evaluator` changes |
| **Repository** | `TraceRepository`, `EvaluationRepository` — isolates storage queries from business logic;<br>DB backend swap (Supabase → Postgres) touches only repositories |

**Rationale**: The system is explicitly designed to grow: new bots, metrics, personas, providers.
Pattern enforcement is the mechanism that keeps growth from accumulating refactoring debt.

## Technology Stack

The approved V1 technology stack is binding. Substitutions or additions MUST be proposed as
constitution amendments (MINOR version bump minimum).

**Framework precedence (binding)**: DeepEval and LangChain/LangGraph are not competing
alternatives — they occupy different layers and are never a choice between one or the other:
- **Primary — DeepEval**: the evaluation engine. Governs everything under Principle II
  (DeepEval-First): metrics, test cases, datasets, synthetic data generation, prompt
  optimization. This is the framework the project is named after and exists to apply.
- **Secondary — LangChain/LangGraph `^1.x`**: the orchestration layer for the bots *being
  evaluated*. Governed by Principle III (LangChain-First), scoped strictly to bot
  orchestration/integration code — never to the evaluator's own architecture.

**Core runtime**: Python `^3.13`, managed with `uv`. `pyproject.toml` (`requires-python = ">=3.13"`,
set 2026-06-22) and `.python-version` (`3.13`) are the binding source of truth; this supersedes the
`^3.11` floor stated in constitution versions prior to 2.1.0, which the repository could not
actually satisfy (`uv sync --python 3.11` is refused under the current `pyproject.toml`).

**Evaluation framework (PRIMARY)**: DeepEval `^4.0.6` — all metrics, Synthesizer,
ConversationSimulator, PromptOptimizer (GEPA / MIPROv2)

**Synthetic document support**: `pypdf`, `docx2txt`, and `chromadb` — runtime dependencies used
by DeepEval's native PDF/DOCX loaders and context-construction pipeline. Project code MUST continue
to delegate document loading and synthetic generation to DeepEval rather than reimplementing these
capabilities.

**Observability**: Langfuse Python SDK `>=4.13.0` (server: self-hosted on VPS)
- Flowise bots: traces arrive automatically via native Langfuse integration (read-only)
- LangChain/LangGraph bots: `langfuse.callback.CallbackHandler` for controlled trace structure
> ⚠ **Breaking-change note**: the SDK's `trace()` method was removed in v4.x. Trace ingestion
> MUST go through `api.ingestion.batch()` with `TraceBody`, not the legacy `trace()` call.

**Bot orchestration (SECONDARY — systems under evaluation)**: LangChain `^1.3.10`,
LangGraph `^1.2.6`, Flowise (self-hosted)
> ⚠ **Hard constraint**: LangChain MUST be `^1.x` (`^1.3.10` minimum) and LangGraph MUST be
> `^1.x` (`^1.2.6` minimum). The 0.x API MUST NOT be used — it is incompatible with the V1
> architecture and the LangChain-First principle (Principle III).

**Persistence**:
- Relational V1: Supabase cloud (Postgres + Auth + RLS) via `supabase>=2.0.0`
- Authenticated Supabase operations MUST use the anonymous project key plus a validated user access
  token so RLS executes in the caller's identity. Service-role credentials MUST NOT be used for
  user-scoped reads, searches, exports, or generation persistence.
- Relational V2+: PostgreSQL self-hosted on VPS (swapped via Repository pattern + `DB_PROVIDER`)
- Vector: `langchain-qdrant>=1.1.0` (server: self-hosted on VPS, API key required) — the native
  LangChain integration (`langchain_qdrant.QdrantVectorStore`) is the direct dependency per
  Principle III (LangChain-First); `qdrant-client` is a transitive dependency only, never
  imported directly outside `langchain-qdrant` itself

**LLM Providers**: OpenAI `>=1.30.0`, Anthropic `>=0.30.0`, OpenRouter — all accessed through
`LLMProviderBase` / `LLMProviderFactory`. Each concrete provider wraps DeepEval's own
`DeepEvalBaseLLM` judge-model class for that provider (`GPTModel`, `AnthropicModel`,
`OpenRouterModel` from `deepeval.models`) per Principle II (DeepEval-First) — the
`ChatOpenAI`/`ChatAnthropic`/`ChatOpenRouter` LangChain chat models MUST NOT be used for this
role; that workaround was replaced once the `deepeval_platform/` package rename made native
`deepeval.models` imports resolvable (see Sync Impact Report). `LLMProviderBase` itself remains
a project-local ABC — its `generate()` returns `tuple[str, TokenUsage]`, which does not match
`DeepEvalBaseLLM.generate() -> str`, so it does NOT inherit `DeepEvalBaseLLM` directly. Every
concrete provider MUST expose `as_deepeval_model() -> DeepEvalBaseLLM` returning the wrapped
native instance, so it can be passed directly to any `Metric(model=...)` as the judge.

**Backend API**: FastAPI `^0.115.0` + Uvicorn

**Frontend**: Next.js `^14.0`, shadcn/ui (CLI-installed), Tailwind CSS `^3.4`, Recharts `^2.12`,
TanStack Table `^8` — dark theme inspired by Confident AI

**Scheduling**: APScheduler `^3.10.0` with cron expressions per bot

**Configuration**: python-dotenv `^1.0.0`, PyYAML `^6.0`

**Testing**: pytest `^8.0.0`, pytest-cov `^5.0.0`, pytest-asyncio `^0.23.0`,
pytest-mock `^3.14.0`

**Containerization**: Docker + Docker Compose (app + Langfuse + Qdrant for local dev)

**Multi-tenant strategy**: V1's production deployment topology serves a single organisation, but
the data and access-control layer MUST be built multi-tenant-ready from day one — this is a
deployment-scale statement, not an exemption from org-scoped enforcement. Every database table
MUST include an `org_id` nullable column from day one to enable V2 multi-tenant activation without
schema migration. `user_id` MUST NEVER be used as a global-scope identifier. Org-id enforcement
(Gate 9: JWT-derived `org_id`, user-scoped RLS, rejection of caller-supplied `org_id`) applies
regardless of how many organisations are actually deployed.

## Quality Gates

Every feature MUST pass all applicable gates before being considered complete:

1. **TDD compliance** — Tests were written before production code, following the RED→GREEN→REFACTOR
   cycle (Principle IV). This MUST be evidenced by at least one of:
   (a) fine-grained commit history showing test-then-implementation ordering, where that commit
   granularity is used; or
   (b) for phase/feature-granularity commits, a documented audit note (e.g. in the feature's
   `research.md`) affirmatively recording, per task, that the test was written, run, observed to
   fail (RED), and then made to pass (GREEN) via live test runs during the implementation session.
   An unsubstantiated claim of having followed TDD, with neither form of evidence present, does
   NOT satisfy this gate.
2. **Coverage** — `pytest-cov` reports ≥ 80% for all new and changed modules.
3. **Zero hardcode** — Grep for hardcoded credentials returns empty on all new/changed files.
4. **Pattern compliance** — New bots, metrics, and providers are added as subclasses only.
   Every new output target is implemented as a `ResultObserver` without changes to `Evaluator`;
   concrete output targets are required only in the feature that introduces them.
5. **DeepEval-first check** — Any code in the evaluation domain (metrics, strategies, trace
   extraction/collection, dataset generation, prompt optimization) is accompanied by a note
   confirming DeepEval's native classes/functions were checked before writing a custom
   implementation (Principle II).
6. **LangChain-first check** — Any code that orchestrates or integrates with a bot under
   evaluation (chains, retrievers, callbacks, loaders, agents, tools) is accompanied by a note
   confirming the LangChain MCP was consulted before writing the implementation (Principle III).
   This gate does NOT apply to evaluation-domain modules — those are covered by Gate 5.
7. **Config completeness** — `.env.example` is updated for every new environment variable
   introduced; `ConfigManager` is the only reader.
8. **Org-id readiness & migration compliance** (persistence tasks) — Every new database table
   includes `org_id` as a nullable column. Every database schema change MUST be committed as a
   versioned SQL migration file in `migrations/` (e.g., `001_evaluation_results.sql`); no schema
   may be applied via manual editor operations — manual steps are untrackable, unreproducible in
   CI, and violate the TDD evidence requirement of Gate 1.
9. **Authentication and RLS** — User-scoped persistence flows MUST validate the Supabase Auth
   access token, derive `org_id` from trusted identity claims, and execute through a user-scoped
   client subject to RLS. Accepting an arbitrary caller-provided `org_id` is not authorization.

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

**Compliance review**: Every PR MUST verify compliance with Principles I–VI and the Quality
Gates section. Complexity deviations MUST be justified in the PR description with explicit
reference to the violated principle and why no simpler path exists.

**Runtime guidance**: See `CLAUDE.md` for agent-specific runtime instructions.

**Version**: 2.1.0 | **Ratified**: 2026-06-19 | **Last Amended**: 2026-07-20

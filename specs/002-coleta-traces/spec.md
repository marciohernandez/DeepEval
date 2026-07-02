# Feature Specification: M2.1 — Coleta de Traces e Estratégias de Avaliação

**Feature Branch**: `002-coleta-traces`

**Created**: 2026-07-02

**Status**: Draft

**Input**: Módulos em escopo para M2.1 — TraceExtractor + EvaluationStrategy

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Trace Collection with Precise Filtering (Priority: P1)

An evaluation pipeline needs to retrieve only the interactions relevant to a specific bot,
within a defined time window, and optionally restricted to interactions with a particular
completion status (fully completed vs. interrupted without a response). The collection
operation shields the pipeline from knowing anything about the underlying observability
platform — it simply declares its filter parameters and receives a clean, structured list
of matching interactions.

**Why this priority**: All evaluation workflows depend on a well-scoped, filtered set of
interactions as their starting point. Without reliable, filtered collection, evaluation runs
either consume irrelevant data or miss the interactions they need to score.

**Independent Test**: Testable by seeding known interactions in the observability platform
with specific bot identifiers, timestamps, and completion statuses, then invoking the
collector with matching filters and verifying only the expected subset is returned.

**Acceptance Scenarios**:

1. **Given** interactions exist for a bot with mixed completion statuses, **When** the
   collector is invoked with `bot_id`, a date range, and `status=completed`, **Then** only
   fully-completed interactions within that date range are returned.
2. **Given** a date range that spans interactions from multiple bots, **When** the collector
   is invoked for a specific `bot_id`, **Then** only interactions belonging to that bot are
   returned.
3. **Given** no interactions match the supplied filter criteria, **When** the collector is
   invoked, **Then** an empty list is returned without raising an error.
4. **Given** the observability platform is unreachable, **When** the collector is invoked,
   **Then** a descriptive error is raised that identifies the connectivity failure.

---

### User Story 2 — Automatic Metric Selection by Bot Type (Priority: P2)

An evaluation orchestrator receives a bot's configuration and needs to know which quality
metrics to apply. It provides the bot type (RAG, agentive, or conversational) and receives
the appropriate metric set without encoding any bot-type branching logic in the orchestrator
itself.

**Why this priority**: Each bot type has fundamentally different interaction patterns and
quality criteria. A unified, pluggable selection layer makes it possible to add new bot types
without modifying the orchestrator or any existing metric configuration.

**Independent Test**: Testable by requesting a metric set for each supported bot type and
asserting the returned list matches the expected composition for that type — independently of
any trace data or live evaluation run.

**Acceptance Scenarios**:

1. **Given** a RAG bot type identifier is provided, **When** the strategy selector is called,
   **Then** a metric set suited to assessing information-retrieval quality and answer
   faithfulness is returned.
2. **Given** an agentive bot type identifier is provided, **When** the strategy selector is
   called, **Then** a metric set suited to assessing tool use and task completion is returned.
3. **Given** a conversational bot type identifier is provided, **When** the strategy selector
   is called, **Then** a metric set suited to assessing multi-turn conversational quality is
   returned.
4. **Given** an unrecognized bot type identifier is provided, **When** the strategy selector
   is called, **Then** a descriptive error is raised that names the unrecognized type and lists
   the supported values.

---

### User Story 3 — Extending Evaluation Coverage for a New Bot Type (Priority: P3)

A developer needs to add evaluation support for a new class of bot without modifying any
existing evaluation code. They declare the new type's metric composition in an isolated
module and register it with the factory. Every existing bot type continues to be evaluated
exactly as before.

**Why this priority**: The bot fleet will grow. Extensibility without regression is a
first-class system requirement — each new bot type must be addable at zero cost to existing
quality coverage.

**Independent Test**: Testable by defining a minimal new strategy, registering it, requesting
it from the factory, and confirming it returns its declared metrics — without re-testing any
existing strategies.

**Acceptance Scenarios**:

1. **Given** a new strategy is registered for a new bot type, **When** that type identifier
   is passed to the factory, **Then** the new strategy is returned and existing strategies
   (RAG, Agent, Conversation) are unaffected.
2. **Given** a new interaction-extraction implementation is defined for a new bot platform,
   **When** it is selected through the same interface as existing implementations, **Then**
   it returns structured interaction records indistinguishable in shape from those produced
   by existing implementations.

---

### Edge Cases

- What happens when an interaction has no bot identifier tag? (Expected: excluded from
  results, not silently assigned to the wrong bot.)
- What happens when the collector is invoked with `start_date` after `end_date`?
- What happens when `StrategyFactory` receives a `None` or empty bot type?
- What happens when two bot types share the same metric category but require different
  sensitivity thresholds? (Thresholds are strategy-level configuration, not metric identity.)

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The trace collector MUST accept `bot_id`, `start_date`, `end_date`, and an
  optional `status` filter (completed / interrupted) as its input parameters.
- **FR-002**: The trace collector MUST delegate all raw data retrieval to `TraceRepository`
  and MUST NOT issue direct calls to the observability platform.
- **FR-003**: When `status=completed` is specified, the collector MUST return only
  interactions that produced a recorded response output; when `status=interrupted`, only
  interactions without a recorded output.
- **FR-004**: The trace collector interface MUST be extensible so that platform-specific
  extraction logic (Flowise vs. LangChain bots) can be encapsulated in separate,
  interchangeable implementations without modifying shared collection behavior.
- **FR-005**: `EvaluationStrategyBase` MUST define a single, stable interface that all
  concrete strategies implement — at minimum a method that returns the ordered list of
  metrics for the given bot type.
- **FR-006**: `RAGStrategy` MUST return a metric set that covers retrieval quality and
  answer faithfulness for RAG bots.
- **FR-007**: `AgentStrategy` MUST return a metric set that covers tool selection and
  task-completion accuracy for agentive bots.
- **FR-008**: `ConversationStrategy` MUST return a metric set that covers conversational
  coherence and response quality for multi-turn bots.
- **FR-009**: `StrategyFactory` MUST select and return the correct strategy instance for
  each registered bot type string.
- **FR-010**: `StrategyFactory` MUST raise a descriptive error for unrecognized bot type
  strings, including the list of supported values in the error message.
- **FR-011**: Adding a new evaluation strategy MUST require only one new strategy module
  plus one registration line in `StrategyFactory` — zero modifications to existing
  strategy implementations.

### Key Entities

- **TraceFilter**: The input value object for trace collection — holds `bot_id`,
  `start_date`, `end_date`, and optional `status`.
- **TraceRecord**: The structured interaction record returned by the collector (defined in
  M1; consumed here without modification).
- **EvaluationStrategy**: The abstract interface every concrete strategy implements,
  exposing the metric list for a given bot type.
- **BotType**: The string or enumerated identifier that classifies a bot as RAG, Agent, or
  Conversation (sourced from `config/bots.yaml`).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Trace collection for any registered bot with any valid filter combination
  completes and returns results within 3 seconds for datasets of up to 500 interactions.
- **SC-002**: Adding a new bot evaluation strategy requires changes to at most 1 new file
  and 1 existing registration line — 0 modifications to existing strategy files.
- **SC-003**: Each of the three built-in strategies (RAG, Agent, Conversation) returns a
  distinct, non-empty metric list; no two strategies return identical sets.
- **SC-004**: `StrategyFactory` returns the correct strategy for every registered bot type
  in 100% of invocations (selection is deterministic).
- **SC-005**: All M2.1 modules achieve ≥ 80% test coverage as measured by the project's
  standard coverage tool.

## Assumptions

- `TraceRepository` (delivered in M1) is the sole data source; the trace collector wraps
  it and introduces no direct observability-platform calls.
- Bot type is stored as a configuration attribute in `config/bots.yaml` and is always
  available when the factory is called.
- Interaction `status` is derived from the existing `TraceRecord` model: a recorded output
  present → completed; no recorded output → interrupted. No third status exists in V1.
- Metric instantiation (threshold assignment, LLM judge selection) is out of scope for
  M2.1; strategies declare which metrics apply, not how they are parameterized.
- The two concrete trace-collector implementations in scope for M2.1 are one for Flowise
  bots and one for LangChain/LangGraph bots, as defined in the project constitution.
- Multi-tenant `org_id` scoping of trace collection is deferred; V1 is single-tenant.

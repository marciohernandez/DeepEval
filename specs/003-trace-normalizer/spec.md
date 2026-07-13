# Feature Specification: M2.2 — TraceNormalizer

**Feature Branch**: `003-trace-normalizer`

**Created**: 2026-07-13

**Status**: Draft

**Input**: Módulos em escopo para M2.2 — TraceNormalizer: `NormalizedTrace` (dataclass com
input, output, context, expected_output, tools_called, messages, metadata), `TraceNormalizer`
(transforma `TraceRecord` de M1 em `NormalizedTrace`), `FieldMapper` (mapeia campos específicos
de cada bot para o formato comum), `ValidationRule` (valida se um `NormalizedTrace` tem os
campos mínimos obrigatórios para cada tipo de avaliação).

## Clarifications

### Session 2026-07-13

- Q: How does the system know how to translate each bot's raw trace fields into the common
  `NormalizedTrace` format? → A: Configuration-driven, per `bot_id`. Each bot declares, in
  `bots.yaml`, where each of the seven standard fields lives in its own raw trace shape. Adding
  a new bot's mapping requires only a config edit — no new `FieldMapper` subclass or other source
  change. Chosen over a fixed one-mapper-per-platform scheme (too rigid if bots on the same
  platform diverge in how they shape their own output) and a one-class-per-bot scheme (unbounded
  code growth as the fleet grows) — matches the project's stated goal that any bot declared in
  `bots.yaml` evaluates without additional code.
- Q: How is a field's location expressed within a `bots.yaml` mapping declaration, given that
  `TraceRecord.input`/`output`/`metadata` are often deeply nested, variable-shape JSON from
  Langfuse? → A: Dot-notation nested path rooted at `input`, `output`, or `metadata` (e.g.
  `output.data.choices.0.message.content`), supporting arbitrary dict-key nesting and numeric
  list indices. Chosen over a top-level-key-only scheme (insufficient for real nested Langfuse
  payloads) and a full JMESPath expression (more power than a location declaration needs, plus an
  added dependency).
- Q: For list-typed fields (`tools_called`, `messages`), does `TraceNormalizer` relocate the raw
  list as-is, or also reshape each item into a common per-item schema? → A: Reshape each item into
  a common schema — `{name, input_parameters, output}` per tool call, `{role, content}` per
  message — independent of the bot's original raw key names. Chosen because leaving items raw
  would let two bots' `tools_called`/`messages` lists carry different internal key names,
  breaking the spec's core promise of a truly common, metric-ready format.
- Q: What does `FieldMapper` do when a declared path resolves to a value of the wrong type for
  that field (e.g. a string where `tools_called` expects a list)? → A: Raise a descriptive error
  identifying the `bot_id`, field, and declared path. Chosen over silently treating it as absent
  or best-effort coercion, consistent with FR-005's existing fail-loud philosophy of never masking
  a configuration or data problem.

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Normalizing Bot Traces into a Common Evaluation Format (Priority: P1)

An evaluation pipeline receives trace records collected by the trace collector (M2.1), each
shaped according to its bot's platform and internal quirks. Before any evaluation metric can
score an interaction, the pipeline needs a single, predictable format with consistently-named
fields — input, output, context, expected output, tools called, messages, and metadata —
regardless of which bot or platform produced the record.

**Why this priority**: Every evaluation strategy (M2.1) depends on a consistent shape; without
normalization, each strategy would need bot-specific handling, breaking the extensibility already
established by the collection and evaluation layers. This is the foundation everything else in
M2.2 builds on.

**Independent Test**: Testable by feeding a known trace record for a bot with a declared field
mapping into the normalizer and confirming the returned normalized trace has the correct values
in the correct standard fields — independently of any live evaluation run.

**Acceptance Scenarios**:

1. **Given** a trace record from a bot with a declared field mapping, **When** it is normalized,
   **Then** the result contains that bot's data correctly placed into the seven standard fields.
2. **Given** a trace record whose bot's field mapping does not declare a source for a particular
   standard field, **When** it is normalized, **Then** that field resolves to a defined empty
   value and normalization completes without error.
3. **Given** a trace record belonging to a bot with no field mapping declared at all, **When**
   normalization is attempted, **Then** a descriptive error identifies the bot and the missing
   mapping — normalization never falls back to a guessed or default mapping.

---

### User Story 2 — Declaring a New Bot's Field Mapping Without Writing Code (Priority: P2)

Whoever manages the bot fleet adds a new bot and needs its traces normalized correctly. They add
a field-mapping declaration to the existing bot configuration file describing where each standard
field lives in that bot's raw trace shape. No new mapping class or code change is required.

**Why this priority**: This is the mechanism that lets normalization scale with the bot fleet —
matching the project's goal that any bot declared in configuration evaluates without additional
code. It depends on User Story 1's normalizer already existing.

**Independent Test**: Testable by declaring a field mapping for a new bot entry in configuration,
feeding a matching trace record through the normalizer, and confirming the mapping is applied
correctly without any source code change.

**Acceptance Scenarios**:

1. **Given** a new bot's field mapping is added to configuration only, **When** a trace for that
   bot is normalized, **Then** all declared fields resolve correctly with no modification to any
   mapping or normalization source code.
2. **Given** two bots on the same platform with different field-mapping declarations, **When**
   each bot's traces are normalized, **Then** each uses its own declared mapping and neither
   affects the other's output.

---

### User Story 3 — Validating Trace Completeness Before Evaluation (Priority: P1)

Before an evaluation strategy (M2.1: RAG / Agent / Conversation) scores a normalized trace, the
pipeline checks whether that trace actually carries the minimum fields that strategy's metrics
require. A RAG trace missing context, or an Agent trace missing the tools called, is flagged
rather than silently scored on incomplete data — which would produce misleading results or fail
unpredictably mid-run.

**Why this priority**: Protecting the trustworthiness of every score the system reports depends
on catching incomplete traces before they reach evaluation — tied with User Story 1 as the gate
that makes the M2.1 metric pipeline safe to run against real data.

**Independent Test**: Testable by constructing normalized traces with deliberately missing fields
for each bot type and confirming the validator correctly flags which are complete or incomplete —
independently of any actual evaluation run.

**Acceptance Scenarios**:

1. **Given** a normalized trace for a RAG bot with context and expected output present, **When**
   validated, **Then** it is reported as valid for RAG evaluation.
2. **Given** a normalized trace for a RAG bot missing context, **When** validated, **Then** it is
   reported as invalid, naming the missing field.
3. **Given** a normalized trace for an Agent bot missing tools called, **When** validated,
   **Then** it is reported as invalid, naming the missing field.
4. **Given** a normalized trace for a Conversation bot missing messages, **When** validated,
   **Then** it is reported as invalid, naming the missing field.
5. **Given** a normalized trace with all fields present, **When** validated against any bot
   type's rule, **Then** it is reported as valid.

---

### Edge Cases

- What happens when a bot's field-mapping declaration points to a location that doesn't exist in
  one specific trace (e.g., no tool was called that turn, so the tool-call section is simply
  absent)? (Expected: the field resolves to a defined empty value — e.g., an empty list for tools
  called — not an error; absence of data at a declared location is normal, not malformed
  configuration.)
- What happens when a bot has a field-mapping declaration but it is only partially filled in
  (some of the seven fields declared, others not)? (Expected: declared fields resolve normally;
  undeclared fields resolve to their defined empty value — same handling as User Story 1,
  Acceptance Scenario 2. Partial declarations are not an error.)
- What happens when the same normalized trace is validated against a bot type's rule it does not
  belong to (e.g., a Conversation trace checked against the RAG rule)? (Expected: validation
  proceeds using whichever bot type rule is requested; the caller is responsible for requesting
  the correct rule for the trace's actual bot type — mismatched requests are a caller error, not
  a validation-layer concern.)
- What happens when a bot's field-mapping declaration points to a location whose resolved value
  has the wrong type for that field (e.g., the `tools_called` path resolves to a string instead
  of a list)? (Expected: `FieldMapper` raises a descriptive error identifying the `bot_id`, field
  name, and declared path — a type mismatch is treated as malformed mapping or data, never
  silently coerced or treated as an absent value.)
- What happens when a declared path's root or an intermediate segment is itself a scalar for one
  specific record (e.g. `TraceRecord.input` is a plain `str` for that call, but the bot's mapping
  declares `input.data.question`), so traversal cannot continue past that segment? (Expected: this
  is handled identically to a missing key — the field resolves to its defined empty value, not an
  error; a scalar blocking further traversal is absence of data at a declared location, same as
  Edge Case 1, not malformed configuration.)

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: `NormalizedTrace` MUST be a dataclass exposing exactly seven fields: `input`,
  `output`, `context`, `expected_output`, `tools_called`, `messages`, and `metadata` — a single,
  platform- and bot-agnostic shape usable by every evaluation strategy (M2.1) and by downstream
  test-case construction (M3).
- **FR-002**: `TraceNormalizer` MUST accept a single `TraceRecord` (M1) belonging to a known
  `bot_id` and return one `NormalizedTrace`, using the field mapping declared for that bot in
  `bots.yaml` — read via `ConfigManager`, never inferred from `bot_id` naming conventions or
  passed by the caller (same selection discipline as M2.1 FR-004).
- **FR-003**: Field-mapping declarations MUST live in `bots.yaml`, one per bot, describing where
  each of the seven standard fields is located within that bot's raw trace data (its `input`,
  `output`, and `metadata`). Each location MUST be expressed as a dot-notation path rooted at one
  of `input`, `output`, or `metadata` (e.g. `output.data.choices.0.message.content`), supporting
  arbitrary dict-key nesting and numeric list indices, including negative indices (e.g. `-1` for
  "last item"), matching Python's own list-indexing semantics. Adding a new bot's mapping MUST
  require zero changes to `FieldMapper` or `TraceNormalizer` source code.
- **FR-004**: `FieldMapper` MUST resolve each field declared in a bot's mapping against that
  bot's raw `TraceRecord` and MUST NOT raise when a declared location is absent from one specific
  record — an absent value normalizes to a defined empty value for that field's type (an empty
  list for `tools_called`/`messages`/`context`, `None` for scalar fields). When a declared
  location resolves to a value of the wrong type for that field (e.g., a scalar found where
  `tools_called` expects a list), `FieldMapper` MUST raise a descriptive error identifying the
  `bot_id`, field name, and declared path — a type mismatch is treated as malformed mapping or
  data, never silently coerced or treated as absent.
- **FR-005**: `TraceNormalizer` MUST raise a descriptive error identifying the `bot_id` when no
  field-mapping declaration exists for that bot at all. Normalization MUST NOT silently fall back
  to a default or guessed mapping.
- **FR-006**: `ValidationRule` MUST accept a `NormalizedTrace` and a `BotType` (M2.1) and report
  whether the trace satisfies the minimum fields that bot type's evaluation strategy requires,
  without raising — the caller decides how to handle an invalid result (skip, flag, log). The
  minimum fields per bot type are:
  - RAG: `input`, `output`, `context`, `expected_output`
  - Agent: `input`, `output`, `tools_called`
  - Conversation: `messages`
- **FR-007**: When a `NormalizedTrace` fails validation, `ValidationRule` MUST report which
  specific required field(s) are missing or empty — never a bare pass/fail with no explanation.
- **FR-008**: Adding a new evaluation type's minimum-field rule MUST require only a new rule
  registration — zero modifications to `TraceNormalizer` or `FieldMapper`, and zero modifications
  to existing bot types' rules.
- **FR-009**: For list-typed fields (`tools_called`, `messages`), `FieldMapper` MUST reshape each
  list item into a common per-item schema, independent of the bot's original raw key names: each
  tool call resolves to `{name, input_parameters, output}` and each message resolves to
  `{role, content}`. This ensures downstream consumers (M2.1 evaluation strategies, M3 test-case
  construction) can rely on identical item shape across every bot, not just identical field names.

### Key Entities

- **NormalizedTrace**: The platform- and bot-agnostic output of `TraceNormalizer`. Fields:
  `input`, `output`, `context`, `expected_output`, `tools_called`, `messages`, `metadata`.
  `tools_called` and `messages` are lists whose items follow a common per-item schema
  (`{name, input_parameters, output}` and `{role, content}` respectively — FR-009), not the bot's
  original raw item shape. Consumed by evaluation strategies (M2.1) and, downstream, by test-case
  construction (M3).
- **TraceNormalizer**: Transforms one `TraceRecord` (M1) into one `NormalizedTrace`, using the
  field mapping declared for that record's `bot_id`.
- **FieldMapper**: Resolves a bot's declared field-mapping against its raw `TraceRecord`, using
  dot-notation paths rooted at `input`, `output`, or `metadata`. A declared location that is
  absent in a specific record yields a defined empty value rather than an error; a location whose
  resolved value has the wrong type for its field raises a descriptive error instead. For
  `tools_called` and `messages`, each list item is reshaped into the common per-item schema
  (FR-009).
- **Field mapping declaration** (in `bots.yaml`): Per-bot configuration naming, for each of the
  seven `NormalizedTrace` fields, where within the raw `TraceRecord` that data lives. Sourced via
  `ConfigManager`, alongside the existing `bot_type` and `platform` fields (M2.1).
- **ValidationRule**: Per-`BotType` rule that checks a `NormalizedTrace` for the minimum fields
  its evaluation strategy needs, reporting missing fields rather than raising.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Adding a new bot's field mapping requires editing only `bots.yaml` — zero source
  code changes to `FieldMapper`, `TraceNormalizer`, or `ValidationRule`.
- **SC-002**: For any bot with a complete field-mapping declaration, normalizing its traces
  succeeds and produces a `NormalizedTrace` with no exceptions in 100% of well-formed
  `TraceRecord` inputs — "well-formed" meaning every declared field-mapping path that is present
  in the record resolves to a value of the type that field expects (FR-004's type-safety
  guarantee); a `TraceRecord` violating this (a genuine type mismatch) is explicitly out of
  scope for SC-002 and is instead covered by FR-004's `FieldMappingTypeError` contract.
- **SC-003**: `ValidationRule` correctly identifies whether a `NormalizedTrace` meets its bot
  type's minimum-field requirement in 100% of cases, across all three built-in bot types.
- **SC-004**: A `NormalizedTrace` failing validation always reports the specific missing
  field(s) — never a bare pass/fail with no explanation.
- **SC-005**: All M2.2 modules achieve ≥ 80% test coverage as measured by the project's standard
  coverage tool.

## Assumptions

- Field-mapping declarations are added per `bot_id` in `bots.yaml`, resolved via `ConfigManager`
  — no code change is needed to onboard a new bot's normalization (per clarification,
  2026-07-13).
- Minimum required fields per `BotType` for `ValidationRule` are derived directly from the metric
  compositions already defined for each strategy in M2.1: RAG needs `context` and
  `expected_output` (contextual precision/recall/relevancy, faithfulness), Agent needs
  `tools_called` (tool correctness), Conversation needs `messages` (multi-turn metrics).
- `TraceNormalizer` operates on one `TraceRecord` at a time; batch iteration over a collected
  list is the caller's (orchestrator's) responsibility — consistent with single responsibility
  per project convention.
- `ValidationRule` is a query, not a gate: it reports validity and missing fields but never
  raises or halts a batch; deciding whether to skip or flag an invalid trace is left to the
  caller (orchestrator, out of scope for M2.2).
- `BotType` (RAG / Agent / Conversation) and its source in `bots.yaml` are already defined by
  M2.1 and are reused here without modification.
- `TraceRecord` (M1, `deepeval_platform/repositories/models.py`) is the sole input to
  `TraceNormalizer`; M2.2 introduces no direct reads from the observability platform.

# Phase 0 Research: M2.2 — TraceNormalizer

**Feature**: [spec.md](spec.md) | **Plan**: [plan.md](plan.md)

## DeepEval-First Check (Principle II, Gate 5)

DeepEval (`^4.0.6`) was consulted before designing any new class in this feature.

- `LLMTestCase` / `ConversationalTestCase` are DeepEval's own metric-input shapes — but they are
  the *destination* format for test-case construction (M3), not a bot-trace normalization layer.
  DeepEval has no native concept of a raw provider/platform trace (Langfuse `TraceRecord`-shaped
  data) or of per-bot field-location configuration; that mapping problem is specific to this
  project's fleet-of-heterogeneous-bots architecture.
- No native `TraceNormalizer`, `FieldMapper`, or trace-validation abstraction exists in DeepEval.
- Conclusion: `NormalizedTrace`, `TraceNormalizer`, `FieldMapper`, and `ValidationRule` are this
  project's own integration-layer classes (same category as M2.1's `TraceExtractor` /
  `EvaluationStrategy`), governed by Principle II's "custom code permitted when no native
  equivalent exists" clause. They sit strictly between M2.1's output (`TraceRecord`) and M3's
  input (DeepEval `LLMTestCase`/`ConversationalTestCase`) — DeepEval classes are not touched by
  this feature at all.

## LangChain-First Check (Principle III, Gate 6)

N/A — this feature introduces no bot-orchestration or integration code (no chains, callbacks,
retrievers, agents, tools). `TraceNormalizer` and `FieldMapper` operate purely on already-collected
`TraceRecord` data structures; they never call LangChain, LangGraph, or Langfuse. Gate 6 does not
apply, consistent with how M2.1 scoped the same gate.

## Decisions

### Decision 1 — `bots.yaml` field-mapping schema

**Decision**: Extend each bot's existing `bots.yaml` entry with a `field_mapping` block. Six of
the seven `NormalizedTrace` fields (`input`, `output`, `expected_output`, `context`,
`tools_called`, `messages`) get a single dot-notation path string rooted at `input`, `output`, or
`metadata` (e.g. `output.data.choices.0.message.content`). `metadata` is passed through in full
(see Decision 5). For the two list fields that require per-item reshaping (FR-009),
`tools_called` and `messages` each get a companion `<field>_item` sub-block declaring, per common
per-item schema key, a path *relative to one list item* (not rooted at input/output/metadata,
since the item is already the traversal root):

```yaml
bots:
  test_rag_bot:
    bot_type: rag
    platform: flowise
    field_mapping:
      input: input.data.question
      output: output.data.answer
      context: output.data.retrieved_contexts
      expected_output: metadata.expected_answer
  test_agent_bot:
    bot_type: agent
    platform: langchain
    field_mapping:
      input: input.data.messages.0.content
      output: output.data.messages.-1.content
      tools_called: output.data.tool_calls
      tools_called_item:
        name: tool_name
        input_parameters: arguments
        output: result
  test_conversation_bot:
    bot_type: conversation
    platform: flowise
    field_mapping:
      messages: output.data.history
      messages_item:
        role: role
        content: text
```

**Rationale**: Matches the clarification session's answer directly (config-driven per `bot_id`,
dot-notation paths, arbitrary nesting + numeric indices). Reuses the existing `bots.yaml` file and
`ConfigManager` flattening mechanism (`ConfigManager._flatten_yaml` already turns nested YAML dicts
into flat dotted keys, e.g. `bots.test_rag_bot.field_mapping.input`) with zero changes to
`ConfigManager` itself — every leaf under `field_mapping` is already a plain string, which is
exactly what `_flatten_yaml` produces a flat key for.

**Alternatives considered**:
- *One mapper class per platform*: rejected per the clarification — too rigid if two bots on the
  same platform diverge in their own raw shape.
- *One mapper class per bot*: rejected per the clarification — unbounded code growth as the fleet
  grows, defeats SC-001.
- *Full JMESPath expressions* for item reshaping too: rejected — more power than needed, adds a
  dependency, and dot-notation-relative-to-item is sufficient since item shapes are flat-ish
  key/value structures in practice.
- *`tools_called_item`/`messages_item` mandatory*: rejected in favor of sensible defaults (Decision
  4) to reduce config boilerplate for the common case.

### Decision 2 — Reading a bot's field mapping through `ConfigManager` (no `ConfigManager` changes)

**Decision**: `FieldMapper` reads one field at a time via
`ConfigManager.instance().get_optional(f"bots.{bot_id}.field_mapping.{field}", default="")`, never
`ConfigManager.instance().get(...)` (which raises on a missing key) — an empty string return means
"this field is undeclared for this bot," which `FieldMapper` turns into the field's defined empty
value per FR-004. Item sub-mappings (`tools_called_item.name`, etc.) are read the same way, one
leaf key at a time.

**Rationale**: `ConfigManager` (Principle V, Singleton, sole config reader) is not modified —
its existing flat key/value store, `get`, and `get_optional` already support this access pattern
with zero source changes to `config_manager.py`, keeping this feature purely additive like M2.1
was. Adding a "fetch whole subtree as dict" method to `ConfigManager` was considered and rejected:
it would be new surface area on a Singleton three other modules already depend on, for a
convenience only `FieldMapper` needs.

**Alternatives considered**:
- *Add `ConfigManager.get_dict(prefix)`*: rejected — unnecessary new API on a shared Singleton for
  a single caller's convenience; per-leaf `get_optional` calls are already O(7) per trace, cheap,
  and keep `ConfigManager` unchanged (lower blast radius, matches Principle I low-coupling intent).
- *`FieldMapper` reads `bots.yaml` directly*: rejected outright — violates Principle V ("no other
  module may read... YAML files directly").

### Decision 3 — Detecting "no field-mapping declared at all" (FR-005) vs. "partial mapping" (edge case)

**Decision**: `TraceNormalizer` first checks whether the bot is known at all
(`ConfigManager.instance().get(f"bots.{bot_id}.bot_type")` — reusing the same existence check
`TraceCollector` already performs in M2.1 for `platform`; raises `ConfigError` if the bot_id itself
is absent from `bots.yaml`, which `TraceNormalizer` re-raises as its own descriptive
`UnmappedBotError`). Given a known bot, `TraceNormalizer` then resolves all seven fields through
`FieldMapper`. If **zero** of the six dot-path-mappable top-level `field_mapping.*` keys (all
`NormalizedTrace` fields except `metadata`, which is always a full passthrough per Decision 5)
resolve to a non-empty string, that is treated as "no field-mapping declared at all" and raises
`UnmappedBotError`
identifying the `bot_id`. If **one or more** resolve, the mapping is treated as (at minimum)
partial, and undeclared fields resolve to their defined empty value per FR-004/Edge Case 2 — no
error.

**Rationale**: This is the only rule that satisfies both User Story 1 Acceptance Scenario 3 ("bot
with no field mapping declared at all" → error) and the Edge Case ("bot has a field-mapping
declaration but only partially filled in" → no error, undeclared fields empty) without requiring
any new "does this key-prefix exist" capability on `ConfigManager` — it only needs the leaf reads
Decision 2 already establishes, checked against the known-bot guard for a genuinely unknown
`bot_id`.

**Alternatives considered**:
- *Require an explicit `field_mapping: {}` marker key to distinguish "declared but empty" from
  "section absent"*: rejected — adds a config-authoring footgun (forgetting the marker silently
  changes behavior) for a distinction the spec's acceptance scenarios never actually require.

### Decision 4 — Default per-item sub-field paths when `tools_called_item` / `messages_item` is omitted

**Decision**: When a bot declares `tools_called` (or `messages`) but omits the companion
`tools_called_item` (or `messages_item`) sub-block, `FieldMapper` falls back to same-name lookup at
the top level of each list item: `name`, `input_parameters`, `output` for tool calls; `role`,
`content` for messages. This is a plain dict-key lookup on the item (not a full dot-path re-parse),
consistent with FR-009's shape but requiring no config at all when a bot's raw items already use
those exact key names.

**Rationale**: Reduces `bots.yaml` boilerplate for the common case where a bot's raw tool/message
items already happen to use the canonical key names, while still allowing full override per bot
when they don't — matches SC-001's goal that onboarding a well-behaved bot stays a minimal config
edit.

**Alternatives considered**: *Always require explicit item sub-mapping*: rejected as needless
verbosity for bots whose raw shape already matches the canonical per-item schema.

### Decision 5 — `metadata` field mapping

**Decision**: `metadata` is not dot-path-mapped like the other six fields; `NormalizedTrace.metadata`
is always the full `TraceRecord.metadata` dict, passed through unchanged. A bot's `field_mapping`
MAY still declare `expected_output` (or others) with a path rooted at `metadata.*` — that is
unaffected, since it addresses a sub-path *within* `TraceRecord.metadata`, not the destination
`NormalizedTrace.metadata` field itself.

**Rationale**: `TraceRecord.metadata` (M1, `repositories/models.py`) is already a free-form dict
carrying whatever the collector captured; there is no "seven-field" sub-structure inside it that
needs relocating the way `input`/`output` payloads do. Re-mapping it field-by-field would require
inventing an eighth nested schema the spec never describes. Passing it through keeps M2.2 additive
and matches FR-001's framing of `metadata` as one of the seven pass-through-shaped fields.

**Alternatives considered**: *Require a `metadata` path in `field_mapping` pointing at a sub-dict*:
rejected — spec's Key Entities section describes `metadata` as a direct `NormalizedTrace` field
with no reshaping requirement analogous to FR-009's list-item reshaping, so passthrough is the
simplest reading consistent with the text.

### Decision 6 — Type-mismatch error type and where raised

**Decision**: Introduce `FieldMappingTypeError(bot_id, field, path, resolved_type)` (raised by
`FieldMapper`, message includes all four) for FR-004's "wrong type at a declared, present
location" case, and `UnmappedBotError(bot_id)` (raised by `TraceNormalizer`, per Decision 3) for
FR-005's "no mapping at all" case. Both are project-local exceptions (not DeepEval or stdlib
types), following the same pattern as M2.1's `InvalidBotTypeError` and M1's `ConfigError` —
descriptive, catch-by-type, message carries all diagnostic fields needed without extra
formatting by the caller.

**Rationale**: Matches the existing codebase convention (`ConfigError`, `InvalidBotTypeError`) of
one small purpose-built exception per failure mode, each named for what a caller would `except`.

**Alternatives considered**: *Reuse a single generic `NormalizationError`*: rejected — collapses
two operationally distinct failures (bad config authoring vs. a data/config type mismatch on one
specific record) into one type, forcing callers to string-match to distinguish them.

### Decision 7 — `ValidationRule` registration mechanism (FR-008)

**Decision**: `ValidationRule` is implemented as one concrete class per `BotType` behind a small
registry dict (`_RULES: dict[BotType, ValidationRuleBase]`), mirroring M2.1's `StrategyFactory`
pattern exactly — `RagValidationRule`, `AgentValidationRule`, `ConversationValidationRule`, each
declaring its own `required_fields()`I a shared `ValidationRuleBase.validate(trace) -> ValidationResult`
does the actual empty/missing check generically over whatever `required_fields()` returns.

**Rationale**: FR-008 requires that adding a new evaluation type's minimum-field rule be "only a
new rule registration — zero modifications to `TraceNormalizer` or `FieldMapper`, and zero
modifications to existing bot types' rules" — this is the Factory + Strategy combination
(Principle VI) already proven for `StrategyFactory`/`EvaluationStrategyBase` in M2.1, reused
verbatim for consistency and because it is the constitution's mandated pattern for exactly this
kind of "new BotType-shaped variant" extension point.

**Alternatives considered**: *A single `ValidationRule` class with an if/BotType-branch inside
`validate()`*: rejected outright — this is precisely the if/else-chain-on-type shape Principle VI
(Factory Method) forbids, and would violate FR-008's "zero modifications to existing rules" bar
the moment a fourth `BotType` is added.

## Summary Table

| # | Decision | Impact |
|---|----------|--------|
| 1 | `bots.yaml` gains `field_mapping` (+ `*_item` sub-blocks) per bot | New config schema, zero `ConfigManager` changes |
| 2 | `FieldMapper` reads one leaf key at a time via `get_optional` | No new `ConfigManager` API |
| 3 | Zero-of-six-fields-declared (excludes `metadata`) ⇒ `UnmappedBotError`; ≥1 ⇒ partial mapping, no error | Resolves FR-005 vs. Edge Case 2 tension |
| 4 | `tools_called_item`/`messages_item` optional, default same-name lookup | Reduces config boilerplate |
| 5 | `metadata` passthrough, not dot-path mapped | Keeps 7-field model simple |
| 6 | `FieldMappingTypeError` + `UnmappedBotError`, project-local | Matches `ConfigError`/`InvalidBotTypeError` convention |
| 7 | `ValidationRule` via registry + per-`BotType` subclasses | Reuses `StrategyFactory` pattern (Principle VI) |

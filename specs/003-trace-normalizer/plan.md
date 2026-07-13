# Implementation Plan: M2.2 — TraceNormalizer

**Branch**: `003-trace-normalizer` | **Date**: 2026-07-13 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/003-trace-normalizer/spec.md`

## Summary

Implement the `normalization` module for M2.2: `NormalizedTrace` (the seven-field, platform- and
bot-agnostic dataclass every evaluation strategy consumes), `TraceNormalizer` (turns one M1
`TraceRecord` into one `NormalizedTrace` using a per-bot `field_mapping` declared in `bots.yaml`),
`FieldMapper` (resolves dot-notation paths against a raw trace, reshaping `tools_called`/`messages`
list items into a common per-item schema), and `ValidationRule` (a `StrategyFactory`-shaped
registry of per-`BotType` minimum-field checks that never raises, only reports). This is the
bridge between M2.1's trace collection/evaluation-strategy layer and M3's DeepEval test-case
construction — purely additive, no changes to any M1 or M2.1 source file.

---

## Technical Context

**Language/Version**: Python 3.13 (pinned), `^3.11` minimum runtime

**Primary Dependencies**: None new. Reuses `PyYAML ^6.0.3` + `python-dotenv` (via the existing
`ConfigManager`, unmodified) and `pytest`/`pytest-cov`/`pytest-mock` (already installed, M1/M2.1).

**Storage**: N/A — `TraceNormalizer` and `FieldMapper` are pure functions over an in-memory
`TraceRecord`; no new DB tables, no new reads from Langfuse or any other external system.

**Testing**: `pytest` + `pytest-cov` (≥80%, SC-005) + `pytest-mock` for `ConfigManager` isolation

**Target Platform**: Linux server (same as M1/M2.1)

**Project Type**: Library / internal pipeline module

**Performance Goals**: No explicit throughput target in spec; normalization is an in-memory,
single-record transform with no I/O, so per-call cost is dominated by dict/list traversal over one
trace's `input`/`output`/`metadata` — expected sub-millisecond per call, no dedicated SC.

**Constraints**:
- `ConfigManager` is the sole config reader — `FieldMapper` never reads `bots.yaml` directly
  (Principle V); `ConfigManager` itself receives zero code changes (research.md Decision 2).
- `TraceNormalizer` never infers a mapping from `bot_id` naming or accepts one from the caller —
  always `ConfigManager`-sourced per `bot_id`, matching M2.1 FR-004's selection discipline (FR-002).
- `FieldMapper` never silently coerces a type mismatch; never silently defaults a genuinely
  malformed mapping into a default guess (FR-004, FR-005).
- `ValidationRule` is a query, not a gate — never raises for an invalid trace, never halts a batch
  (FR-006, spec Assumptions).

**Scale/Scope**: V1 single-tenant; `TraceNormalizer.normalize()` operates on exactly one
`TraceRecord` per call — batch iteration over a collected list is the caller's (orchestrator's)
responsibility, same single-responsibility split M2.1 established for `TraceCollector`.

---

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked post-design below.*

### Pre-Design Check

| Gate | Status | Notes |
|------|--------|-------|
| 1. TDD compliance | ✅ PASS | Plan mandates RED→GREEN→REFACTOR; test files precede implementation files in task order below |
| 2. Coverage ≥80% | ✅ PASS | Enforced via `--cov-fail-under=80` in CI; quickstart.md lists the coverage command (SC-005) |
| 3. Zero hardcode | ✅ PASS | No credentials involved anywhere in this feature; `ConfigManager.instance()` remains sole config reader |
| 4. Pattern compliance | ✅ PASS | `ValidationRule` reuses the exact Factory+Strategy registry shape already proven by `StrategyFactory`/`EvaluationStrategyBase` (research.md Decision 7) |
| 5. DeepEval-first | ✅ PASS | DeepEval checked (2026-07-13, research.md) for a native raw-trace-normalization or field-mapping abstraction. None exists — `NormalizedTrace`/`TraceNormalizer`/`FieldMapper`/`ValidationRule` are this project's own integration layer bridging M2.1's `TraceRecord` to M3's DeepEval test-case model, same category as M2.1's own `TraceExtractor`/`EvaluationStrategy` |
| 6. LangChain-first | N/A | M2.2 introduces no bot-orchestration/integration code (no chains, callbacks, retrievers, or other LangChain components touched) — out of this gate's scope per Principle III, same as M2.1 |
| 7. Config completeness | ✅ PASS | No new `.env` keys; `bots.yaml` gains a `field_mapping` block per bot (+ optional `*_item` sub-blocks) — documented in quickstart.md; `ConfigManager` itself is unchanged |
| 8. Org-id readiness | N/A | No new DB tables in M2.2 |

### Post-Design Re-Check

All gates remain PASS after Phase 1 design:
- `normalization` is a new, self-contained module with no circular deps — it imports only
  `evaluation.bot_type.BotType`/`InvalidBotTypeError` and `repositories.models.TraceRecord` from
  existing packages, and neither `collection` nor `evaluation/strategies` import anything from
  `normalization` (Principle I — single responsibility, low coupling; see data-model.md's
  dependency graph).
- `UnmappedBotError` / `FieldMappingTypeError` follow the existing `ConfigError`/
  `InvalidBotTypeError` convention exactly — no new exception-handling pattern introduced.
- `ValidationRule.check()` raising `InvalidBotTypeError` for a `bot_type` that cannot be coerced
  to `BotType` at all is adopted by convention from M2.1's `StrategyFactory.create()` (same
  exception, same coercion call) — not a behavior spec.md derives independently; spec.md's own
  Edge Cases section covers only a *mismatched-but-valid* bot-type request (Edge Case 3), which
  `ValidationRule` handles by design with no cross-check (spec Assumptions).
- `ValidationRule._REGISTRY` makes a 4th `BotType`'s rule a one-class + one-line-registration
  change (FR-008), verified by a dedicated extensibility test (mirrors M2.1's Phase E).
- Zero modifications to any M1 or M2.1 source file — confirmed by the Project Structure below
  listing only new files.

---

## Project Structure

### Documentation (this feature)

```text
specs/003-trace-normalizer/
├── plan.md              # This file
├── research.md          # Phase 0 output — DeepEval/LangChain-first checks + 7 decisions
├── data-model.md        # Phase 1 output — entities, ABCs, module dependency graph
├── quickstart.md        # Phase 1 output — validation scenarios
├── contracts/           # Phase 1 output — typed interface definitions
│   ├── normalized_trace.py
│   ├── field_mapper.py
│   ├── trace_normalizer.py
│   └── validation_rule.py
└── tasks.md             # Phase 2 output (/speckit-tasks — NOT created here)
```

### Source Code (repository root)

```text
deepeval_platform/
├── normalization/                        # NEW — M2.2
│   ├── __init__.py
│   ├── models.py                        # NormalizedTrace, ToolCall, Message
│   ├── errors.py                         # UnmappedBotError, FieldMappingTypeError
│   ├── field_mapper.py                  # FieldMapper
│   ├── trace_normalizer.py              # TraceNormalizer
│   └── validation/
│       ├── __init__.py
│       ├── result.py                     # ValidationResult
│       ├── rule_base.py                  # ValidationRuleBase ABC
│       ├── rules/
│       │   ├── __init__.py
│       │   ├── rag_rule.py               # RagValidationRule
│       │   ├── agent_rule.py             # AgentValidationRule
│       │   └── conversation_rule.py      # ConversationValidationRule
│       └── rule_registry.py             # ValidationRule (registry facade)
│
├── config/config_manager.py            # M1 — unchanged
├── evaluation/bot_type.py               # M2.1 — unchanged (reused for BotType)
└── repositories/models.py               # M1 — unchanged (reused for TraceRecord)

config/
└── bots.yaml                           # UPDATED — add field_mapping (+ *_item) per bot entry

tests/
└── unit/
    └── normalization/                    # NEW
        ├── __init__.py
        ├── test_models.py
        ├── test_field_mapper.py
        ├── test_trace_normalizer.py
        ├── test_new_bot_config_only.py
        └── validation/
            ├── __init__.py
            ├── test_rag_rule.py
            ├── test_agent_rule.py
            ├── test_conversation_rule.py
            ├── test_validation_rule_registry.py
            └── test_validation_rule_extensibility.py
```

**Structure Decision**: Single-project layout (Option 1), same as M2.1. One new domain package
(`normalization`) at the same level as `collection` and `evaluation`. No changes to any M1 or
M2.1 source file — M2.2 is purely additive, consistent with the project's established pattern of
one new package per milestone.

---

## Complexity Tracking

No constitution violations. All additions are new modules/subclasses following established M1/M2.1
patterns (Singleton `ConfigManager` reuse, Factory+Strategy registry for `ValidationRule`,
project-local descriptive exceptions).

---

## Implementation Phases

### Phase A — Core Models & Errors (TDD order)

**A1 — `NormalizedTrace`, `ToolCall`, `Message`**
- Write `test_models.py` (RED): exactly seven `NormalizedTrace` fields (FR-001); default
  factories give `[]` for `context`/`tools_called`/`messages`, `None` for scalars, `{}` for
  `metadata`; `ToolCall`/`Message` expose their three/two fields
- Implement `deepeval_platform/normalization/models.py`
- Green + refactor

**A2 — `UnmappedBotError`, `FieldMappingTypeError`**
- Write `test_errors.py` (RED): each exception's message contains `bot_id` (+ `field`/`path`/
  `resolved_type` for the type-mismatch error) — a dedicated test per constitution Principle IV
  (every production module gets its own preceding RED test; behavior is exercised again
  end-to-end by `test_field_mapper.py`/`test_trace_normalizer.py` in Phase B/C, but that is not a
  substitute for `errors.py`'s own unit test)
- Implement `deepeval_platform/normalization/errors.py`
- Green + refactor

---

### Phase B — `FieldMapper` (TDD order)

**B1 — Path resolution + defined-empty-value behavior**
- Write `test_field_mapper.py` (RED, using `pytest-mock` to stub `ConfigManager.instance()`):
  - Resolves a declared scalar path rooted at `input`/`output`/`metadata`
  - Resolves a declared path with numeric list-index segments
  - Declared path absent from one record → defined empty value, no error (FR-004)
  - Declared list-typed field (`context`/`tools_called`/`messages`) resolving to a non-list →
    `FieldMappingTypeError` naming `bot_id`, field, path (FR-004)
  - `tools_called`/`messages` items reshaped per explicit `*_item` sub-mapping (FR-009)
  - `tools_called`/`messages` items reshaped via Decision 4 same-name default when `*_item`
    is omitted
- Implement `deepeval_platform/normalization/field_mapper.py`
- Green + refactor

---

### Phase C — `TraceNormalizer` (TDD order)

**C1 — Normalize with full / partial / missing mappings**
- Write `test_trace_normalizer.py` (RED, `pytest-mock` for `ConfigManager`):
  - Known bot, full mapping → correct `NormalizedTrace` in all seven fields (US1 Scenario 1)
  - Known bot, partial mapping → undeclared fields at defined empty value, no error (US1
    Scenario 2, Edge Case 2)
  - Unknown `bot_id` → `UnmappedBotError` naming the bot (US1 Scenario 3)
  - Known bot, zero declared `field_mapping.*` keys → `UnmappedBotError` (FR-005, Decision 3)
- Implement `deepeval_platform/normalization/trace_normalizer.py`
- Green + refactor

**C2 — Config-only bot onboarding (US2)**
- Write `test_new_bot_config_only.py` (RED): a fixture `bots.yaml` fragment declares a new bot's
  mapping; normalizing its trace resolves correctly with zero source changes (US2 Scenario 1);
  two same-platform bots with distinct mappings each resolve independently (US2 Scenario 2)
- No new production code — this phase validates the extensibility contract Phases A–C already
  deliver (mirrors M2.1's Phase E)

---

### Phase D — `ValidationRule` (TDD order)

**D1 — `ValidationResult`, `ValidationRuleBase`**
- Write `test_rag_rule.py` / `test_agent_rule.py` / `test_conversation_rule.py` (RED): each
  concrete rule's `required_fields()`; `validate()` reports `is_valid=True` with no missing
  fields when all required fields present (US3 Scenario 5); reports the specific missing
  field(s) by name when absent/empty (US3 Scenarios 2, 3, 4; FR-007)
- Implement `deepeval_platform/normalization/validation/result.py`,
  `validation/rule_base.py`, `validation/rules/rag_rule.py`, `agent_rule.py`,
  `conversation_rule.py`
- Green + refactor

**D2 — `ValidationRule` registry facade**
- Write `test_validation_rule_registry.py` (RED): `check()` dispatches to the correct rule per
  `BotType`; raw-string `bot_type` coercion works (matches `StrategyFactory.create()`); a
  mismatched bot-type request still just runs that rule, no cross-check (Edge Case); complete
  trace valid against any bot type's rule (US3 Scenario 1)
- Implement `deepeval_platform/normalization/validation/rule_registry.py`
- Green + refactor

**D3 — Extensibility proof (FR-008)**
- Write `test_validation_rule_extensibility.py` (RED): a throwaway 4th `ValidationRuleBase`
  subclass resolves via a local registry instance without any change to
  `RagValidationRule`/`AgentValidationRule`/`ConversationValidationRule`,
  `TraceNormalizer`, or `FieldMapper`
- No new production code — validates the registry's extension contract

---

### Phase E — `bots.yaml` Update

**E1 — Add `field_mapping` declarations**
- Extend the three existing `config/bots.yaml` entries (`test_rag_bot`, `test_agent_bot`,
  `test_conversation_bot`) with `field_mapping` blocks per research.md Decision 1's example —
  needed for the manual/REPL smoke test in quickstart.md and to keep the fixture bots usable
  end-to-end from M2.1 through M2.2

---

### Phase F — Coverage Gate

```bash
uv run pytest tests/unit/normalization/ \
    --cov=deepeval_platform/normalization \
    --cov-report=term-missing --cov-fail-under=80
```

Must pass before feature is considered complete (SC-005).

---

## Key Design Decisions (Summary)

See [research.md](research.md) for full rationale.

| # | Decision | Where |
|---|----------|--------|
| 1 | `bots.yaml` gains `field_mapping` + `*_item` sub-blocks per bot, dot-notation paths rooted at `input`/`output`/`metadata` | research §Decision 1 |
| 2 | `FieldMapper` reads one leaf key at a time via `ConfigManager.get_optional` — zero `ConfigManager` changes | research §Decision 2 |
| 3 | Zero-of-six-fields-declared (excludes `metadata`) ⇒ `UnmappedBotError`; ≥1 declared ⇒ partial mapping, undeclared fields empty | research §Decision 3 |
| 4 | `tools_called_item`/`messages_item` optional — default same-name lookup on each item | research §Decision 4 |
| 5 | `metadata` is always a full passthrough of `TraceRecord.metadata` — not dot-path mapped | research §Decision 5 |
| 6 | `FieldMappingTypeError` (FieldMapper) + `UnmappedBotError` (TraceNormalizer), project-local, `ConfigError`-style | research §Decision 6 |
| 7 | `ValidationRule` via registry dict + per-`BotType` subclasses, mirrors `StrategyFactory` | research §Decision 7 |

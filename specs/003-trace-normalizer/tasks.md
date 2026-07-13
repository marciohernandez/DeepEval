---

description: "Task list for M2.2 — TraceNormalizer"
---

# Tasks: M2.2 — TraceNormalizer

**Input**: Design documents from `/media/marcio/AKT/Projects/DeepEval/specs/003-trace-normalizer/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md (all present)

**Tests**: Included — plan.md mandates TDD (RED→GREEN→REFACTOR) for every production module,
per constitution Principle IV (NON-NEGOTIABLE).

**Organization**: Tasks are grouped by user story (US1, US2, US3) per spec.md priorities.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: Maps task to US1/US2/US3 from spec.md
- File paths are exact and repo-root-relative

## Path Conventions

Single project layout (per plan.md): `deepeval_platform/normalization/` for source,
`tests/unit/normalization/` for tests, `config/bots.yaml` for the shared bot config.

---

## Phase 1: Setup

**Purpose**: Create the package skeleton so subsequent tasks have somewhere to write files.

- [X] T001 Create `deepeval_platform/normalization/__init__.py`,
  `deepeval_platform/normalization/validation/__init__.py`, and
  `deepeval_platform/normalization/validation/rules/__init__.py` (empty package markers, no logic)
- [X] T002 [P] Create `tests/unit/normalization/__init__.py` and
  `tests/unit/normalization/validation/__init__.py` (empty package markers)

**Checkpoint**: Package skeleton exists; no circular deps introduced (plan.md confirms
`normalization` imports only `evaluation.bot_type.BotType` and `repositories.models.TraceRecord`).

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: `NormalizedTrace`/`ToolCall`/`Message` (FR-001) and the two project-local exceptions
are imported by every module in US1, US2, and US3 — nothing else can be built first.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T003 [P] Write `tests/unit/normalization/test_models.py` (RED): `NormalizedTrace` exposes
  exactly the seven fields `input`, `output`, `context`, `expected_output`, `tools_called`,
  `messages`, `metadata` (FR-001); default factory gives `[]` for `context`/`tools_called`/
  `messages`, `None` for `input`/`output`/`expected_output`, `{}` for `metadata`; `ToolCall`
  exposes `name`/`input_parameters`/`output`; `Message` exposes `role`/`content`
- [X] T004 [P] Write `tests/unit/normalization/test_errors.py` (RED): `UnmappedBotError(bot_id)`'s
  message contains the `bot_id`; `FieldMappingTypeError(bot_id, field, path, resolved_type)`'s
  message contains all four of `bot_id`, `field`, `path`, and `resolved_type` — both exceptions
  are asserted to carry every diagnostic field a caller would need without reformatting (matches
  the `ConfigError`/`InvalidBotTypeError` convention)
- [X] T005 Implement `deepeval_platform/normalization/models.py` (`NormalizedTrace`, `ToolCall`,
  `Message` dataclasses per contracts/normalized_trace.py) — make T003 pass (depends on: T003)
- [X] T006 Implement `deepeval_platform/normalization/errors.py` (`UnmappedBotError(bot_id)`,
  `FieldMappingTypeError(bot_id, field, path, resolved_type)`), following the
  `ConfigError`/`InvalidBotTypeError` convention in `deepeval_platform/config/config_manager.py`
  and `deepeval_platform/evaluation/bot_type.py` — make T004 pass (depends on: T004)

**Checkpoint**: `models.py` and `errors.py` are GREEN, each behind its own passing test. All
three user stories can now proceed.

---

## Phase 3: User Story 1 — Normalizing Bot Traces into a Common Evaluation Format (Priority: P1) 🎯 MVP

**Goal**: `TraceNormalizer.normalize()` turns one `TraceRecord` into one `NormalizedTrace` using
the field mapping declared for that bot in `bots.yaml` (FR-002 through FR-005, FR-009).

**Independent Test**: Feed a known trace record for a bot with a declared field mapping into
`TraceNormalizer` and confirm the returned `NormalizedTrace` has correct values in the correct
standard fields — no live evaluation run required.

### Tests for User Story 1 (write first, ensure they FAIL before implementation)

- [X] T007 [P] [US1] Write `tests/unit/normalization/test_field_mapper.py` (RED, using
  `mocker.patch("deepeval_platform.config.config_manager.ConfigManager.instance", ...)` per the
  pattern in `tests/unit/collection/test_trace_collector.py`):
  - resolves a declared scalar path rooted at `input`/`output`/`metadata`
  - resolves a declared path with numeric list-index segments (e.g. `output.data.messages.0.content`),
    including negative indices (e.g. `output.data.messages.-1.content` for "last item", per FR-003)
  - declared path absent from one record → field's defined empty value, no error (FR-004)
  - declared path whose root or an intermediate segment is a scalar for one record (traversal
    cannot continue) → field's defined empty value, no error, same handling as an absent key
    (spec.md Edge Cases)
  - declared list-typed field (`context`/`tools_called`/`messages`) resolving to a non-list →
    `FieldMappingTypeError` naming `bot_id`, field, and path (FR-004)
  - `tools_called`/`messages` items reshaped into `ToolCall`/`Message` per explicit
    `tools_called_item`/`messages_item` sub-mapping (FR-009)
  - `tools_called`/`messages` items reshaped via same-name default lookup when the `*_item`
    sub-block is omitted (research.md Decision 4)
  - resolved `metadata` field always equals `record.metadata` verbatim, regardless of any
    `field_mapping.*` declarations for this bot — passthrough, never dot-path mapped
    (research.md Decision 5)
- [X] T008 [P] [US1] Write `tests/unit/normalization/test_trace_normalizer.py` (RED, same
  `ConfigManager` mocking pattern):
  - known bot, full mapping → correct `NormalizedTrace` in all seven fields (US1 Scenario 1)
  - known bot, partial mapping → undeclared fields at defined empty value, no error (US1
    Scenario 2, Edge Case 2)
  - unknown `bot_id` → `UnmappedBotError` naming the bot (US1 Scenario 3)
  - known bot, zero declared `field_mapping.*` keys → `UnmappedBotError` (FR-005, research.md
    Decision 3)

### Implementation for User Story 1

- [X] T009 [US1] Implement `deepeval_platform/normalization/field_mapper.py` (`FieldMapper` per
  contracts/field_mapper.py: `resolve_all`, `resolve_field`, `_resolve_path`,
  `_reshape_list_items`; reads each `field_mapping` leaf one at a time via
  `ConfigManager.instance().get_optional(...)`, never a bulk-subtree read) — make T007 pass
  (depends on: T005, T006, T007)
- [X] T010 [US1] Implement `deepeval_platform/normalization/trace_normalizer.py`
  (`TraceNormalizer.normalize()` per contracts/trace_normalizer.py: confirms the bot is known via
  `ConfigManager.instance().get(f"bots.{bot_id}.bot_type")`, delegates all field resolution to
  `FieldMapper.resolve_all`, raises `UnmappedBotError` when the bot is unknown or has zero
  declared fields) — make T008 pass (depends on: T009, T008)

**Checkpoint**: User Story 1 is fully functional and independently testable — a known bot with a
declared mapping normalizes correctly; an unmapped bot raises a descriptive error.

---

## Phase 4: User Story 2 — Declaring a New Bot's Field Mapping Without Writing Code (Priority: P2)

**Goal**: Confirm a new bot's field mapping, added to `bots.yaml` config only, normalizes
correctly with zero changes to `FieldMapper` or `TraceNormalizer` source (FR-003, SC-001).

**Independent Test**: Declare a field mapping for a new bot entry in a fixture config, feed a
matching trace record through `TraceNormalizer`, and confirm the mapping is applied correctly
without any source code change.

### Tests for User Story 2

- [X] T011 [US2] Write `tests/unit/normalization/test_new_bot_config_only.py` (RED, stubbing
  `ConfigManager.instance()` with a fixture `bots.yaml`-shaped fragment for a bot not present in
  the real `config/bots.yaml`):
  - a new bot's field mapping declared only in the fixture config normalizes correctly with zero
    modification to any `normalization` source file (US2 Scenario 1)
  - two bots on the same platform with different field-mapping declarations each resolve using
    only their own mapping, independently of the other (US2 Scenario 2)
  - No new production code in this phase — it validates the extensibility contract Phase 3
    already delivers (depends on: T009, T010)

**Checkpoint**: User Stories 1 AND 2 both work independently — onboarding a new bot requires only
a `bots.yaml` edit.

---

## Phase 5: User Story 3 — Validating Trace Completeness Before Evaluation (Priority: P1)

**Goal**: `ValidationRule.check(trace, bot_type)` reports whether a `NormalizedTrace` has the
minimum fields its bot type's evaluation strategy needs, naming any missing fields, and never
raises for an invalid trace (FR-006, FR-007, FR-008).

**Independent Test**: Construct normalized traces with deliberately missing fields for each bot
type and confirm the validator correctly flags which are complete or incomplete — no actual
evaluation run required.

### Tests for User Story 3 (write first, ensure they FAIL before implementation)

- [X] T012 [P] [US3] Write `tests/unit/normalization/validation/test_rag_rule.py` (RED):
  `RagValidationRule.required_fields()` returns `["input", "output", "context",
  "expected_output"]`; complete RAG trace → `is_valid=True`, empty `missing_fields` (US3 Scenario
  1); missing/empty `context` → `is_valid=False`, `"context"` in `missing_fields` (US3 Scenario 2)
- [X] T013 [P] [US3] Write `tests/unit/normalization/validation/test_agent_rule.py` (RED):
  `AgentValidationRule.required_fields()` returns `["input", "output", "tools_called"]`; missing
  `tools_called` → `is_valid=False`, `"tools_called"` in `missing_fields` (US3 Scenario 3)
- [X] T014 [P] [US3] Write `tests/unit/normalization/validation/test_conversation_rule.py` (RED):
  `ConversationValidationRule.required_fields()` returns `["messages"]`; missing `messages` →
  `is_valid=False`, `"messages"` in `missing_fields` (US3 Scenario 4)

### Implementation for User Story 3 — rules

- [X] T015 [P] [US3] Implement `deepeval_platform/normalization/validation/result.py`
  (`ValidationResult` dataclass: `is_valid: bool`, `missing_fields: list[str]` per
  contracts/validation_rule.py)
- [X] T016 [US3] Implement `deepeval_platform/normalization/validation/rule_base.py`
  (`ValidationRuleBase` ABC: abstract `required_fields()`; concrete `validate(trace)` that checks
  each required field for `None`/empty-list/empty-dict/empty-string and returns a
  `ValidationResult`, never raises — FR-006, FR-007) (depends on: T005, T015)
- [X] T017 [P] [US3] Implement `deepeval_platform/normalization/validation/rules/rag_rule.py`
  (`RagValidationRule(ValidationRuleBase)`) — make T012 pass (depends on: T016, T012)
- [X] T018 [P] [US3] Implement `deepeval_platform/normalization/validation/rules/agent_rule.py`
  (`AgentValidationRule(ValidationRuleBase)`) — make T013 pass (depends on: T016, T013)
- [X] T019 [P] [US3] Implement
  `deepeval_platform/normalization/validation/rules/conversation_rule.py`
  (`ConversationValidationRule(ValidationRuleBase)`) — make T014 pass (depends on: T016, T014)

### Implementation for User Story 3 — registry facade

- [X] T020 [US3] Write `tests/unit/normalization/validation/test_validation_rule_registry.py`
  (RED): `ValidationRule.check()` dispatches to the correct rule per `BotType`; raw-string
  `bot_type` coercion works (matches `StrategyFactory.create()`); an unrecognized `bot_type`
  raises `InvalidBotTypeError`; a complete trace is valid against any bot type's rule (US3
  Scenario 5); requesting a mismatched bot-type rule against a trace still just runs that rule,
  no cross-check (Edge Case) (depends on: T017, T018, T019)
- [X] T021 [US3] Implement `deepeval_platform/normalization/validation/rule_registry.py`
  (`ValidationRule` registry facade: `_REGISTRY: dict[BotType, ValidationRuleBase]` mapping
  `BotType.RAG`/`AGENT`/`CONVERSATION` to their rule instances, `check()` classmethod coercing
  `bot_type` via `BotType(...)` exactly like `StrategyFactory.create()` in
  `deepeval_platform/evaluation/strategy_factory.py`) — make T020 pass (depends on: T020)

### Extensibility proof (FR-008)

- [X] T022 [US3] Write
  `tests/unit/normalization/validation/test_validation_rule_extensibility.py` (RED/pass
  immediately given T021): a throwaway 4th `ValidationRuleBase` subclass resolves via a local
  registry subclass (mirroring `tests/unit/evaluation/test_strategy_factory_extensibility.py`'s
  `_ExtendedFactory` pattern) without any change to `RagValidationRule`, `AgentValidationRule`,
  `ConversationValidationRule`, `TraceNormalizer`, or `FieldMapper` — no new production code
  (depends on: T021)

**Checkpoint**: All three user stories are independently functional and testable.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Wire the real `config/bots.yaml` for end-to-end/manual verification and confirm the
coverage gate (SC-005).

- [X] T023 [P] Extend `config/bots.yaml`'s three existing entries (`test_rag_bot`,
  `test_agent_bot`, `test_conversation_bot`) with `field_mapping` (+ `tools_called_item`/
  `messages_item`) blocks per research.md Decision 1 / quickstart.md's example — needed for the
  manual/REPL smoke test, not for the unit suite (which mocks `ConfigManager`)
- [X] T024 Run the quickstart.md manual/REPL smoke test scenarios 1–4 against the updated
  `config/bots.yaml` (depends on: T010, T021, T023)
- [X] T025 Run the coverage gate and confirm ≥80% (SC-005):
  `uv run pytest tests/unit/normalization/ --cov=deepeval_platform/normalization --cov-report=term-missing --cov-fail-under=80`
  (depends on: T005, T006, T009, T010, T011, T015–T019, T021, T022)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **Foundational (Phase 2)**: Depends on Setup — BLOCKS all user stories
- **User Story 1 (Phase 3)**: Depends on Foundational only
- **User Story 2 (Phase 4)**: Depends on Foundational + User Story 1 (`TraceNormalizer`/
  `FieldMapper` must exist to validate config-only onboarding against them)
- **User Story 3 (Phase 5)**: Depends on Foundational only (does not need US1/US2's
  `TraceNormalizer`/`FieldMapper` — only `NormalizedTrace` and `BotType`); can run in parallel
  with Phase 3/4 if staffed separately
- **Polish (Phase 6)**: Depends on Phases 3, 4, and 5 all being complete

### User Story Dependencies

- **User Story 1 (P1)**: No dependency on US2/US3 — the MVP
- **User Story 2 (P2)**: Depends on US1's `TraceNormalizer`/`FieldMapper` existing; adds no new
  production code
- **User Story 3 (P1, tied with US1)**: No dependency on US1/US2 — only needs `NormalizedTrace`
  (Phase 2) and `BotType` (existing M2.1). Independently testable and deliverable in parallel with
  US1

### Within Each User Story

- Tests written and confirmed failing before implementation (RED→GREEN→REFACTOR, per plan.md and
  constitution Principle IV) — every production module in this list, including `errors.py`, has
  its own preceding test task
- Models/errors (Phase 2) before mappers/normalizers (Phase 3) before registry (Phase 5)
- Story complete before moving to the next priority (if working sequentially)

### Parallel Opportunities

- T002 (test package markers) can run parallel to T001 (source package markers)
- T003 (models test) and T004 (errors test) can run in parallel — different files, no shared
  dependency; T005 (implement models) and T006 (implement errors) can likewise run in parallel
  once their respective tests exist
- T007 and T008 (Phase 3 test files) can run in parallel — different files
- T012, T013, T014 (Phase 5 rule tests) can run in parallel — different files
- T017, T018, T019 (Phase 5 rule implementations) can run in parallel once T016 lands
- Phase 3 (US1) and Phase 5 (US3) can be staffed in parallel — US3 does not depend on
  `TraceNormalizer`/`FieldMapper`, only on Phase 2's `NormalizedTrace`

---

## Parallel Example: Phase 2 (Foundational)

```bash
# Launch together — different files, no shared dependency:
Task: "Write tests/unit/normalization/test_models.py (T003)"
Task: "Write tests/unit/normalization/test_errors.py (T004)"

# Once both are RED, launch together — each implementation only needs its own test:
Task: "Implement deepeval_platform/normalization/models.py (T005)"
Task: "Implement deepeval_platform/normalization/errors.py (T006)"
```

## Parallel Example: User Story 3 rule tests

```bash
# Launch together — different files:
Task: "Write tests/unit/normalization/validation/test_rag_rule.py (T012)"
Task: "Write tests/unit/normalization/validation/test_agent_rule.py (T013)"
Task: "Write tests/unit/normalization/validation/test_conversation_rule.py (T014)"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (CRITICAL — blocks all stories)
3. Complete Phase 3: User Story 1
4. **STOP and VALIDATE**: run `uv run pytest tests/unit/normalization/test_field_mapper.py
   tests/unit/normalization/test_trace_normalizer.py -v`
5. This alone proves the core normalization promise (SC-002) before layering onboarding (US2) or
   validation (US3) on top

### Incremental Delivery

1. Setup + Foundational → foundation ready
2. Add User Story 1 → test independently (MVP: any known bot normalizes)
3. Add User Story 3 in parallel or next → test independently (validation reports missing fields)
4. Add User Story 2 → test independently (config-only onboarding confirmed)
5. Polish: wire real `config/bots.yaml`, run the coverage gate

### Parallel Team Strategy

With two developers after Foundational is done:
- Developer A: User Story 1 (Phase 3) → then User Story 2 (Phase 4)
- Developer B: User Story 3 (Phase 5), independent of Developer A's work
- Both converge on Phase 6 (Polish)

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Verify each test file fails before implementing the module it targets — this applies to every
  production file in this list, `errors.py` included (T004 before T006)
- `ConfigManager` itself receives zero source changes anywhere in this feature (research.md
  Decision 2) — only `config/bots.yaml` content changes (T023)
- No M1 or M2.1 source file is modified by any task in this list (plan.md Post-Design Re-Check)

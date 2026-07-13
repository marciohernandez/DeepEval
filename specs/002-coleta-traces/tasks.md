---

description: "Task list for M2.1 — Coleta de Traces e Estratégias de Avaliação"
---

# Tasks: M2.1 — Coleta de Traces e Estratégias de Avaliação

**Input**: Design documents from `/specs/002-coleta-traces/`

**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md), [data-model.md](data-model.md), [contracts/](contracts/), [quickstart.md](quickstart.md)

**Tests**: Tests are **NOT optional** for this project — Principle IV (TDD — NON-NEGOTIABLE) of the constitution mandates RED→GREEN→REFACTOR for every task with production code. Every implementation task below has a corresponding test task that MUST be written first and MUST fail before the implementation task begins.

**Organization**: Tasks are grouped by user story (spec.md). `collection` (US1) and `evaluation` (US2) are independent modules with zero cross-dependencies (see [data-model.md](data-model.md) Module Dependency Graph) — they can be implemented in either order or in parallel. US3 has no new production code; it validates the extensibility already delivered by US1/US2's ABC + Factory/Strategy patterns.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3)
- File paths are exact and relative to the repository root

## Path Conventions

Single-project layout (confirmed in plan.md): `deepeval_platform/` for source, `tests/unit/` and `tests/integration/` for tests, `config/bots.yaml` for bot declarations.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Create the two new package skeletons declared in plan.md's Project Structure. No logic yet.

- [X] T001 [P] Create `collection` package skeleton: `deepeval_platform/collection/__init__.py`, `deepeval_platform/collection/extractors/__init__.py`, `tests/unit/collection/__init__.py`
- [X] T002 [P] Create `evaluation` package skeleton: `deepeval_platform/evaluation/__init__.py`, `deepeval_platform/evaluation/strategies/__init__.py`, `tests/unit/evaluation/__init__.py`

---

## Phase 2: Foundational (Blocking Prerequisites)

**None required.** Per data-model.md's Module Dependency Graph, `collection` and `evaluation` share no code beyond M1 modules that already exist (`ConfigManager`, `TraceRepository`, `TraceRecord`). Each user story below builds its own foundation (value objects → ABC → concrete classes) inside its own phase.

---

## Phase 3: User Story 1 — Trace Collection with Precise Filtering (Priority: P1) 🎯 MVP

**Goal**: Deliver `TraceCollector`, which returns a filtered, capped, platform-aware list of `TraceRecord` for a single bot, shielding callers from Langfuse/platform details.

**Independent Test**: Seed known interactions with specific `bot_id`, timestamps, and completion statuses; invoke `TraceCollector.collect()` with matching filters; verify only the expected subset is returned (see quickstart.md Scenarios 1–4).

### Tests for User Story 1 (write first — MUST fail before implementation)

- [X] T003 [P] [US1] Write `InteractionStatus`/`TraceFilter` tests in `tests/unit/collection/test_trace_filter.py` — valid construction; `start_date >= end_date` → `ValueError`; empty `bot_id` → `ValueError` (per contracts/trace_filter.py)
- [X] T004 [P] [US1] Write `TraceExtractorBase` ABC test in `tests/unit/collection/test_extractor_base.py` — cannot instantiate directly; `extract()` is enforced abstract
- [X] T005 [P] [US1] Write `FlowiseExtractor` tests in `tests/unit/collection/test_flowise_extractor.py` — `status=COMPLETED` filter; `status=INTERRUPTED` filter; `status=None` returns all; empty input returns `[]`
- [X] T006 [P] [US1] Write `LangChainExtractor` tests in `tests/unit/collection/test_langchain_extractor.py` — same scenarios as T005, validating LangChain-specific output shape handling
- [X] T007 [P] [US1] Write `TraceCollector` tests (using `pytest-mock` to mock `TraceRepository` and `ConfigManager`) in `tests/unit/collection/test_trace_collector.py` — selects `FlowiseExtractor` when `platform=flowise`; selects `LangChainExtractor` when `platform=langchain`; emits `DEBUG` log on extractor selection; returns most-recent 500 when >500 records match; emits `WARNING` when truncating; returns `[]` on empty result; propagates `TraceRepositoryError` immediately with no retry

### Implementation for User Story 1

- [X] T008 [US1] Implement `InteractionStatus` + `TraceFilter` in `deepeval_platform/collection/trace_filter.py` (makes T003 pass)
- [X] T009 [US1] Implement `TraceExtractorBase` ABC in `deepeval_platform/collection/extractor_base.py` (makes T004 pass; depends on T008 for the `InteractionStatus` type)
- [X] T010 [P] [US1] Implement `FlowiseExtractor` in `deepeval_platform/collection/extractors/flowise_extractor.py` (makes T005 pass; depends on T009)
- [X] T011 [P] [US1] Implement `LangChainExtractor` in `deepeval_platform/collection/extractors/langchain_extractor.py` (makes T006 pass; depends on T009)
- [X] T012 [US1] Implement `TraceCollector` in `deepeval_platform/collection/trace_collector.py` — reads `bots.<bot_id>.platform` from `ConfigManager.instance()` at call-time, selects extractor, delegates to `TraceRepository.get_by_date_range()`, sorts by `start_time` desc, caps at `MAX_INTERACTIONS=500` (makes T007 pass; depends on T008, T010, T011)
- [X] T013 [US1] Populate `config/bots.yaml` with bot entries, each declaring `bot_type` and `platform` fields — the file is currently empty (0 bytes), so this creates the entries rather than augmenting pre-existing ones (see quickstart.md for example entries; depends on T012; required before T014)

### Integration Test for User Story 1

- [X] T014 [US1] Write `tests/integration/test_trace_collector_integration.py` (marked `pytest.mark.integration`, requires live Langfuse) covering all four acceptance scenarios from spec.md User Story 1 — status filter, bot isolation, empty result, connectivity failure — plus a fifth scenario asserting SC-001: seed (or synthesize via a 500-record fixture) up to 500 interactions and assert `collect()` completes within 3 seconds wall-clock (see quickstart.md Scenarios 1–4; depends on T013)

**Checkpoint**: `TraceCollector` is fully functional and independently testable — User Story 1 delivers a working MVP. ✅ Validated 2026-07-13: 36/36 unit tests pass, 100% coverage on `deepeval_platform/collection/`, 181/181 full unit suite green (no regressions). Integration test (T014) written but not executed against a live Langfuse instance in this session.

---

## Phase 4: User Story 2 — Automatic Metric Selection by Bot Type (Priority: P2)

**Goal**: Deliver `StrategyFactory`, which maps a `BotType` (or coercible raw string) to the correct `EvaluationStrategyBase` implementation, without any bot-type branching in calling code.

**Independent Test**: Request a metric set for each supported bot type via `StrategyFactory.create()` and assert the returned list matches the expected composition — independent of any trace data (see quickstart.md Strategy Smoke Test).

### Tests for User Story 2 (write first — MUST fail before implementation)

- [X] T015 [P] [US2] Write `BotType`/`InvalidBotTypeError` tests in `tests/unit/evaluation/test_bot_type.py` — valid lowercase coercion (`"rag"`, `"agent"`, `"conversation"`); `"unknown"` → `ValueError`; `None` → `ValueError`; `""` → `ValueError`
- [X] T016 [P] [US2] Write `EvaluationStrategyBase` ABC test in `tests/unit/evaluation/test_strategy_base.py` — cannot instantiate directly; `get_metrics()` is enforced abstract
- [X] T017 [P] [US2] Write `RAGStrategy` tests in `tests/unit/evaluation/test_rag_strategy.py` — `get_metrics()` returns non-empty `list[str]`; stable across calls; contains retrieval/faithfulness metric names
- [X] T018 [P] [US2] Write `AgentStrategy` tests in `tests/unit/evaluation/test_agent_strategy.py` — same shape checks; set is distinct from `RAGStrategy`'s
- [X] T019 [P] [US2] Write `ConversationStrategy` tests in `tests/unit/evaluation/test_conversation_strategy.py` — same shape checks; set is distinct from `RAGStrategy`'s and `AgentStrategy`'s
- [X] T020 [P] [US2] Write `StrategyFactory` tests in `tests/unit/evaluation/test_strategy_factory.py` — correct concrete type for each `BotType`; raw-string coercion works; `"unknown"`/`None`/`""` all raise `InvalidBotTypeError` with received value + supported list in the message; repeated `create()` calls for the same `BotType` return the same concrete class every time (SC-004 determinism)

### Implementation for User Story 2

- [X] T021 [US2] Implement `BotType` + `InvalidBotTypeError` in `deepeval_platform/evaluation/bot_type.py` (makes T015 pass)
- [X] T022 [US2] Implement `EvaluationStrategyBase` ABC in `deepeval_platform/evaluation/strategy_base.py` (makes T016 pass)
- [X] T023 [P] [US2] Implement `RAGStrategy` in `deepeval_platform/evaluation/strategies/rag_strategy.py` returning `["answer_relevancy", "faithfulness", "contextual_precision", "contextual_recall", "contextual_relevancy"]` (makes T017 pass; depends on T022)
- [X] T024 [P] [US2] Implement `AgentStrategy` in `deepeval_platform/evaluation/strategies/agent_strategy.py` returning `["tool_correctness", "task_completion"]` (makes T018 pass; depends on T022)
- [X] T025 [P] [US2] Implement `ConversationStrategy` in `deepeval_platform/evaluation/strategies/conversation_strategy.py` returning `["conversation_completeness", "turn_relevancy"]` (makes T019 pass; depends on T022)
- [X] T026 [US2] Implement `StrategyFactory` in `deepeval_platform/evaluation/strategy_factory.py` with `_registry` mapping each `BotType` to its strategy class; `create()` coerces raw strings via `BotType(value)` and re-raises `ValueError` as `InvalidBotTypeError` (makes T020 pass; depends on T021, T023, T024, T025)

**Checkpoint**: `StrategyFactory` is fully functional and independently testable — User Story 2 delivers metric selection with zero branching in caller code. ✅ Validated 2026-07-13: 41/41 unit tests pass, 100% coverage on `deepeval_platform/evaluation/`, 222/222 full unit suite green (no regressions).

---

## Phase 5: User Story 3 — Extending Evaluation Coverage for a New Bot Type (Priority: P3)

**Goal**: Prove the extensibility contract already built into US1/US2 (Strategy + Factory + ABC patterns) — no new production module is needed, only tests that exercise the extension points.

**Independent Test**: Define a minimal new strategy/extractor at test scope, register/select it through the existing interfaces, and confirm it behaves correctly without re-testing or modifying the existing built-in implementations.

- [X] T027 [P] [US3] Write extensibility test in `tests/unit/evaluation/test_strategy_factory_extensibility.py` — define a throwaway `EvaluationStrategyBase` subclass, register it into a copy of `StrategyFactory._registry` (or via a test-local factory instance), confirm it's returned correctly and that `RAGStrategy`/`AgentStrategy`/`ConversationStrategy` remain unaffected (validates FR-011, SC-002, spec.md US3 Acceptance Scenario 1)
- [X] T028 [P] [US3] Write extensibility test in `tests/unit/collection/test_extractor_extensibility.py` — define a throwaway `TraceExtractorBase` subclass, confirm `.extract()` returns `TraceRecord` results indistinguishable in shape from `FlowiseExtractor`/`LangChainExtractor` output (validates spec.md US3 Acceptance Scenario 2)

**Checkpoint**: All three user stories are independently functional and verified — extensibility is proven, not just assumed. ✅ Validated 2026-07-13: 6/6 extensibility tests pass, 228/228 full unit suite green (no regressions).

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Final gates required before the feature is considered complete (SC-005, quickstart.md).

- [X] T029 [P] Run the coverage gate: `uv run pytest tests/unit/collection/ tests/unit/evaluation/ --cov=deepeval_platform/collection --cov=deepeval_platform/evaluation --cov-report=term-missing --cov-fail-under=80` — MUST pass ≥80% (SC-005). ✅ 2026-07-13: 100.00% coverage (124/124 statements), 83/83 tests pass. Note: required `-o addopts=""` to override pyproject.toml's global `--cov=deepeval_platform` (which otherwise dilutes the total with unrelated M1 modules).
- [X] T030 Execute [quickstart.md](quickstart.md) end-to-end: unit test runs, Strategy Smoke Test, and (if a live Langfuse instance is available) the four integration scenarios — confirm all documented outcomes match. ✅ 2026-07-13: unit runs 83/83 pass; Strategy Smoke Test passes (RAG/Agent/Conversation metric sets confirmed distinct, `InvalidBotTypeError` path confirmed). Langfuse reachable (`https://langfuse.bigdates.com.br/` health check 200) — ran all 5 integration tests (4 acceptance scenarios + SC-001 perf), all pass. Caveat: no traces are seeded for `test_rag_bot` yet, so Scenarios 1–2 (status filter, bot isolation) likely passed vacuously (empty result set) rather than proving real filtering against seeded data — seed per quickstart.md's "Integration Test Run" section for a stronger check.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — T001 and T002 can run in parallel immediately
- **Foundational (Phase 2)**: Empty — no blocking prerequisites beyond Setup
- **User Story 1 (Phase 3)**: Depends on T001 only
- **User Story 2 (Phase 4)**: Depends on T002 only — fully independent of Phase 3, can proceed in parallel
- **User Story 3 (Phase 5)**: Depends on Phase 3 (T012) and Phase 4 (T026) both being complete — it tests extension points on both layers
- **Polish (Phase 6)**: Depends on Phases 3, 4, and 5 all being complete

### Within User Story 1

`T003 → T008` · `T004 → T009 (needs T008)` · `T005 → T010 (needs T009)` · `T006 → T011 (needs T009)` · `T007 → T012 (needs T008, T010, T011)` · `T013 (needs T012)` · `T014 (needs T013)`

### Within User Story 2

`T015 → T021` · `T016 → T022` · `T017 → T023 (needs T022)` · `T018 → T024 (needs T022)` · `T019 → T025 (needs T022)` · `T020 → T026 (needs T021, T023, T024, T025)`

### Parallel Opportunities

- T001 and T002 (Setup) — different packages
- T003–T007 (US1 tests) — different files, no cross-dependencies
- T010 and T011 (Flowise vs. LangChain extractors) — different files, same dependency (T009)
- T015–T020 (US2 tests) — different files, no cross-dependencies
- T023, T024, T025 (RAG/Agent/Conversation strategies) — different files, same dependency (T022)
- T027 and T028 (US3 extensibility tests) — different files, different layers
- Phase 3 (US1) and Phase 4 (US2) can be worked entirely in parallel by two developers — zero shared files

---

## Parallel Example: User Story 1

```bash
# Launch all US1 tests together (RED phase):
Task: "Write InteractionStatus/TraceFilter tests in tests/unit/collection/test_trace_filter.py"
Task: "Write TraceExtractorBase ABC test in tests/unit/collection/test_extractor_base.py"
Task: "Write FlowiseExtractor tests in tests/unit/collection/test_flowise_extractor.py"
Task: "Write LangChainExtractor tests in tests/unit/collection/test_langchain_extractor.py"
Task: "Write TraceCollector tests in tests/unit/collection/test_trace_collector.py"

# After T009 (TraceExtractorBase) is green, launch both extractors together:
Task: "Implement FlowiseExtractor in deepeval_platform/collection/extractors/flowise_extractor.py"
Task: "Implement LangChainExtractor in deepeval_platform/collection/extractors/langchain_extractor.py"
```

## Parallel Example: User Story 2

```bash
# Launch all US2 tests together (RED phase):
Task: "Write BotType/InvalidBotTypeError tests in tests/unit/evaluation/test_bot_type.py"
Task: "Write EvaluationStrategyBase ABC test in tests/unit/evaluation/test_strategy_base.py"
Task: "Write RAGStrategy tests in tests/unit/evaluation/test_rag_strategy.py"
Task: "Write AgentStrategy tests in tests/unit/evaluation/test_agent_strategy.py"
Task: "Write ConversationStrategy tests in tests/unit/evaluation/test_conversation_strategy.py"
Task: "Write StrategyFactory tests in tests/unit/evaluation/test_strategy_factory.py"

# After T022 (EvaluationStrategyBase) is green, launch all three strategies together:
Task: "Implement RAGStrategy in deepeval_platform/evaluation/strategies/rag_strategy.py"
Task: "Implement AgentStrategy in deepeval_platform/evaluation/strategies/agent_strategy.py"
Task: "Implement ConversationStrategy in deepeval_platform/evaluation/strategies/conversation_strategy.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (T001–T002)
2. Phase 2: Foundational — nothing to do, proceed directly
3. Complete Phase 3: User Story 1 (T003–T014)
4. **STOP and VALIDATE**: run `uv run pytest tests/unit/collection/ -v` and the quickstart.md integration scenarios (if Langfuse is reachable)
5. `TraceCollector` is usable standalone as the MVP

### Incremental Delivery

1. Setup → Foundational (trivial) → Foundation ready
2. Add User Story 1 (collection layer) → validate independently → MVP
3. Add User Story 2 (evaluation layer) → validate independently → metric selection ready for M3 (`MetricFactory`)
4. Add User Story 3 (extensibility proof) → validate independently → confidence for future bot types
5. Phase 6: coverage gate + full quickstart run → feature complete (SC-005)

### Parallel Team Strategy

With two developers: one takes User Story 1 (collection), the other User Story 2 (evaluation) — zero shared files, both depend only on Setup. Merge before starting User Story 3, since its tests touch both layers.

---

## Notes

- TDD is **NON-NEGOTIABLE** here (constitution Principle IV) — every test task above MUST be written and observed failing before its paired implementation task begins.
- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Commit after each RED→GREEN→REFACTOR cycle (test task + implementation task pair), not after the whole phase
- Avoid: vague tasks, same-file conflicts, cross-story dependencies that break independence (US3 is the sole exception, by design — it validates cross-layer extensibility)

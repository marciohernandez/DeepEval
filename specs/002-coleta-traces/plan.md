# Implementation Plan: M2.1 — Coleta de Traces e Estratégias de Avaliação

**Branch**: `002-coleta-traces` | **Date**: 2026-07-09 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/002-coleta-traces/spec.md`

## Summary

Implement the `TraceCollector` pipeline and `EvaluationStrategy` registry for M2.1. The collector wraps the M1 `TraceRepository` with filtered, capped, platform-aware trace retrieval using the Strategy pattern (`FlowiseExtractor` / `LangChainExtractor`). The evaluation layer introduces `BotType`, `EvaluationStrategyBase`, three concrete strategies (RAG, Agent, Conversation), and `StrategyFactory` — delivering the metric-selection contract that `MetricFactory` (M3) will consume.

---

## Technical Context

**Language/Version**: Python 3.13 (pinned), `^3.11` minimum runtime

**Primary Dependencies**:
- `langfuse >=4.13.0` — already installed (M1); SDK `v4.13+` uses `api.ingestion.batch()` + `TraceBody` (no deprecated `trace()`)
- `PyYAML ^6.0`, `python-dotenv ^1.0.0` — already installed (M1)
- `pytest ^8.0.0`, `pytest-cov ^5.0.0`, `pytest-mock ^3.14.0` — already installed (M1)

**Storage**: N/A for M2.1 — no new DB tables (reads from Langfuse via `TraceRepository`)

**Testing**: `pytest` + `pytest-cov` (≥80%) + `pytest-mock` for isolation

**Target Platform**: Linux server (same as M1)

**Project Type**: Library / internal pipeline module

**Performance Goals**: Trace collection for up to 500 interactions completes in ≤3 seconds (SC-001)

**Constraints**:
- No direct Langfuse calls — all reads via `TraceRepository` (FR-002)
- No retry in collector — fail fast (FR-002, research Decision 2)
- Hard cap of 500 interactions, most recent first (FR-001)
- `ConfigManager` is the sole config reader — no module reads bots.yaml directly (Principle V)

**Scale/Scope**: V1 single-tenant, single-bot-per-collect() call; pagination deferred to V2

---

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked post-design below.*

### Pre-Design Check

| Gate | Status | Notes |
|------|--------|-------|
| 1. TDD compliance | ✅ PASS | Plan mandates RED→GREEN→REFACTOR; test files listed before implementation files in task order |
| 2. Coverage ≥80% | ✅ PASS | Enforced via `--cov-fail-under=80` in CI; quickstart.md lists coverage command |
| 3. Zero hardcode | ✅ PASS | `ConfigManager.instance()` is sole config reader; no credentials in source |
| 4. Pattern compliance | ✅ PASS | Strategy pattern for extractors + evaluation strategies; Factory for `StrategyFactory` |
| 5. DeepEval-first | ✅ PASS | DeepEval checked (2026-07-09) for a native trace-extraction or bot-type-strategy abstraction. None exists — `TraceExtractor` and `EvaluationStrategy` are this project's own integration layer over DeepEval's metric/test-case model; custom implementation required (documented in research.md) |
| 6. LangChain-first | N/A | M2.1 introduces no bot-orchestration/integration code (no chains, callbacks, retrievers, or other LangChain components touched) — out of this gate's scope per Principle III |
| 7. Config completeness | ✅ PASS | No new `.env` keys; `bots.yaml` gains `bot_type` + `platform` fields per bot — documented in quickstart.md |
| 8. Org-id readiness | N/A | No new DB tables in M2.1 |

### Post-Design Re-Check

All gates remain PASS after Phase 1 design:
- `collection` and `evaluation` are separate modules with no circular deps (Principle I — single responsibility)
- `TraceExtractorBase` + `EvaluationStrategyBase` ABCs guarantee extensibility (Principle VI)
- `TraceCollector` never imports from `evaluation`; `evaluation` never imports from `collection` (low coupling)
- `StrategyFactory._registry` dict makes adding a new bot type a one-line change (FR-011)

---

## Project Structure

### Documentation (this feature)

```text
specs/002-coleta-traces/
├── plan.md              # This file
├── research.md          # Phase 0 output — DeepEval-first check + 6 decisions
├── data-model.md        # Phase 1 output — entities, ABCs, module dep graph
├── quickstart.md        # Phase 1 output — validation scenarios
├── contracts/           # Phase 1 output — typed interface definitions
│   ├── trace_filter.py
│   ├── trace_extractor.py
│   ├── trace_collector.py
│   └── evaluation_strategy.py
└── tasks.md             # Phase 2 output (/speckit-tasks — NOT created here)
```

### Source Code (repository root)

```text
deepeval_platform/
├── collection/                          # NEW — M2.1
│   ├── __init__.py
│   ├── trace_filter.py                  # InteractionStatus, TraceFilter
│   ├── extractor_base.py               # TraceExtractorBase ABC
│   ├── extractors/
│   │   ├── __init__.py
│   │   ├── flowise_extractor.py        # FlowiseExtractor
│   │   └── langchain_extractor.py      # LangChainExtractor
│   └── trace_collector.py             # TraceCollector (MAX_INTERACTIONS=500)
│
├── evaluation/                          # NEW — M2.1
│   ├── __init__.py
│   ├── bot_type.py                      # BotType(str,Enum), InvalidBotTypeError
│   ├── strategy_base.py                 # EvaluationStrategyBase ABC
│   ├── strategies/
│   │   ├── __init__.py
│   │   ├── rag_strategy.py             # RAGStrategy
│   │   ├── agent_strategy.py           # AgentStrategy
│   │   └── conversation_strategy.py    # ConversationStrategy
│   └── strategy_factory.py             # StrategyFactory
│
├── config/config_manager.py            # M1 — unchanged
├── repositories/
│   ├── models.py                       # M1 — TraceRecord unchanged
│   └── trace_repository.py            # M1 — TraceRepository unchanged
└── observability/langfuse_client.py    # M1 — LangfuseClient unchanged

config/
└── bots.yaml                           # UPDATED — add bot_type + platform per entry

tests/
├── unit/
│   ├── collection/                      # NEW
│   │   ├── __init__.py
│   │   ├── test_trace_filter.py
│   │   ├── test_extractor_base.py
│   │   ├── test_flowise_extractor.py
│   │   ├── test_langchain_extractor.py
│   │   ├── test_trace_collector.py
│   │   └── test_extractor_extensibility.py
│   └── evaluation/                      # NEW
│       ├── __init__.py
│       ├── test_bot_type.py
│       ├── test_strategy_base.py
│       ├── test_rag_strategy.py
│       ├── test_agent_strategy.py
│       ├── test_conversation_strategy.py
│       ├── test_strategy_factory.py
│       └── test_strategy_factory_extensibility.py
└── integration/
    └── test_trace_collector_integration.py  # NEW
```

**Structure Decision**: Single-project layout (Option 1). Two new domain packages (`collection`, `evaluation`) at the same level as existing M1 packages. No changes to M1 source files — M2.1 is purely additive.

---

## Complexity Tracking

No constitution violations. All additions are new subclasses or new modules following established M1 patterns.

---

## Implementation Phases

### Phase A — Collection Layer (TDD order)

**A1 — `InteractionStatus` + `TraceFilter`**
- Write `test_trace_filter.py` (RED): valid construction; `start >= end` → `ValueError`; empty `bot_id` → `ValueError`
- Implement `deepeval_platform/collection/trace_filter.py`
- Green + refactor

**A2 — `TraceExtractorBase` ABC**
- Write `test_extractor_base.py` (RED): cannot instantiate directly; abstract method enforced
- Implement `deepeval_platform/collection/extractor_base.py`
- Green + refactor

**A3 — `FlowiseExtractor`**
- Write `test_flowise_extractor.py` (RED): completed filter; interrupted filter; no filter; empty input; records without output treated as interrupted
- Implement `deepeval_platform/collection/extractors/flowise_extractor.py`
- Green + refactor

**A4 — `LangChainExtractor`**
- Write `test_langchain_extractor.py` (RED): same shape tests as Flowise; validates LangChain output dict structure
- Implement `deepeval_platform/collection/extractors/langchain_extractor.py`
- Green + refactor

**A5 — `TraceCollector`**
- Write `test_trace_collector.py` (RED, using `pytest-mock`):
  - Selects `FlowiseExtractor` when `platform=flowise`
  - Selects `LangChainExtractor` when `platform=langchain`
  - Emits DEBUG log on extractor selection
  - Returns most-recent 500 when >500 records
  - Emits WARNING when truncating
  - Returns [] on empty result
  - Propagates `TraceRepositoryError` immediately (no retry)
- Implement `deepeval_platform/collection/trace_collector.py`
- Green + refactor

**A6 — Update `config/bots.yaml`**
- Add `bot_type` and `platform` fields to each existing bot entry

---

### Phase B — Evaluation Layer (TDD order)

**B1 — `BotType` + `InvalidBotTypeError`**
- Write `test_bot_type.py` (RED): valid lowercase coercion; `"unknown"` → `ValueError`; `None` → `ValueError`; `""` → `ValueError`; `InvalidBotTypeError` message contains received + supported list
- Implement `deepeval_platform/evaluation/bot_type.py`
- Green + refactor

**B2 — `EvaluationStrategyBase` ABC**
- Write `test_strategy_base.py` (RED): cannot instantiate; abstract method enforced
- Implement `deepeval_platform/evaluation/strategy_base.py`
- Green + refactor

**B3 — `RAGStrategy`**
- Write `test_rag_strategy.py` (RED): non-empty list; all strings; stable across calls; contains expected metric names
- Implement `deepeval_platform/evaluation/strategies/rag_strategy.py`
- Green + refactor

**B4 — `AgentStrategy`**
- Write `test_agent_strategy.py` (RED): same shape tests; distinct from RAG set
- Implement `deepeval_platform/evaluation/strategies/agent_strategy.py`
- Green + refactor

**B5 — `ConversationStrategy`**
- Write `test_conversation_strategy.py` (RED): same shape tests; distinct from RAG and Agent sets
- Implement `deepeval_platform/evaluation/strategies/conversation_strategy.py`
- Green + refactor

**B6 — `StrategyFactory`**
- Write `test_strategy_factory.py` (RED): correct type for each BotType; raw string coercion works; `"unknown"` → `InvalidBotTypeError`; `None` → `InvalidBotTypeError`; `""` → `InvalidBotTypeError`; error message correct
- Implement `deepeval_platform/evaluation/strategy_factory.py`
- Green + refactor

---

### Phase C — Integration Tests

**C1 — `test_trace_collector_integration.py`**
- Requires live Langfuse; runs with `pytest -m integration`
- Covers all four acceptance scenarios from spec User Story 1 (see quickstart.md)
- Plus a fifth scenario asserting SC-001: `collect()` completes within 3 seconds for up to 500 interactions
- Uses real `TraceRepository`; no mocks

---

### Phase E — Extensibility Proof (US3)

**E1 — `test_strategy_factory_extensibility.py`**
- Defines a throwaway `EvaluationStrategyBase` subclass; confirms it resolves correctly without touching `RAGStrategy`/`AgentStrategy`/`ConversationStrategy` (FR-011, SC-002)

**E2 — `test_extractor_extensibility.py`**
- Defines a throwaway `TraceExtractorBase` subclass; confirms `.extract()` output shape matches `FlowiseExtractor`/`LangChainExtractor` (spec User Story 3, Acceptance Scenario 2)

No new production modules in this phase — it validates the extensibility contract already delivered by Phases A and B.

---

### Phase F — Coverage Gate

```bash
uv run pytest tests/unit/collection/ tests/unit/evaluation/ \
    --cov=deepeval_platform/collection --cov=deepeval_platform/evaluation \
    --cov-report=term-missing --cov-fail-under=80
```

Must pass before feature is considered complete (SC-005).

---

## Key Design Decisions (Summary)

See [research.md](research.md) for full rationale.

| # | Decision | Where |
|---|----------|--------|
| 1 | `TraceExtractorBase.extract(records, status)` — batch interface | research §Decision 1 |
| 2 | Collector reads platform from ConfigManager at call-time, not construction | research §Decision 2 |
| 3 | `bots.<bot_id>.platform` and `bots.<bot_id>.bot_type` keys in bots.yaml | research §Decision 3 |
| 4 | Metric sets: RAG=5 metrics, Agent=2, Conversation=2 (all distinct) | research §Decision 4 |
| 5 | Sort by `start_time` desc in-process; None timestamps sink to end | research §Decision 5 |
| 6 | `InteractionStatus` co-located with `TraceFilter` in collection layer | research §Decision 6 |

# Phase 1 Data Model: M2.2 — TraceNormalizer

**Feature**: [spec.md](spec.md) | **Plan**: [plan.md](plan.md) | **Research**: [research.md](research.md)

## Module Dependency Graph

```
deepeval_platform/normalization/
├── models.py               # NormalizedTrace, ToolCall, Message (dataclasses)
├── errors.py                # UnmappedBotError, FieldMappingTypeError
├── field_mapper.py         # FieldMapper
├── trace_normalizer.py     # TraceNormalizer
└── validation/
    ├── __init__.py
    ├── result.py            # ValidationResult
    ├── rule_base.py         # ValidationRuleBase (ABC)
    ├── rules/
    │   ├── rag_rule.py       # RagValidationRule
    │   ├── agent_rule.py     # AgentValidationRule
    │   └── conversation_rule.py  # ConversationValidationRule
    └── rule_registry.py     # ValidationRule (registry facade, mirrors StrategyFactory)
```

Dependency direction (no cycles):
- `trace_normalizer.py` → `field_mapper.py`, `models.py`, `errors.py`,
  `deepeval_platform.config.config_manager.ConfigManager`, `deepeval_platform.repositories.models.TraceRecord`
- `field_mapper.py` → `models.py`, `errors.py`, `ConfigManager`
- `validation/*` → `models.py` (reads `NormalizedTrace`), `deepeval_platform.evaluation.bot_type.BotType`
- `normalization` package never imports from `collection` or `evaluation/strategies` — only from
  `evaluation.bot_type` (the shared `BotType` enum) and `repositories.models` (shared `TraceRecord`),
  same low-coupling shape M2.1 established between `collection` and `evaluation`.

## Entities

### `NormalizedTrace` (dataclass, `models.py`)

| Field | Type | Default when undeclared/absent (FR-004) |
|-------|------|---|
| `input` | `Any \| None` | `None` |
| `output` | `Any \| None` | `None` |
| `context` | `list[Any]` | `[]` |
| `expected_output` | `Any \| None` | `None` |
| `tools_called` | `list[ToolCall]` | `[]` |
| `messages` | `list[Message]` | `[]` |
| `metadata` | `dict` | `{}` (Decision 5 — always full `TraceRecord.metadata` passthrough) |

Exactly the seven fields FR-001 mandates — no more, no less.

### `ToolCall` (dataclass, `models.py`)

Common per-tool-call schema (FR-009): `name: Any`, `input_parameters: Any`, `output: Any`.

### `Message` (dataclass, `models.py`)

Common per-message schema (FR-009): `role: Any`, `content: Any`.

### `TraceNormalizer` (`trace_normalizer.py`)

```python
class TraceNormalizer:
    def normalize(self, record: TraceRecord) -> NormalizedTrace: ...
```

- Looks up `bots.{record.bot_id}.bot_type` via `ConfigManager.instance()` to confirm the bot is
  known; a missing bot_id propagates as `UnmappedBotError` (Decision 3).
- Delegates all seven field resolutions to `FieldMapper.resolve_all(record)`.
- If `FieldMapper` reports zero declared fields (Decision 3), raises `UnmappedBotError`.
- Never falls back to a guessed mapping (FR-005) — purely a lookup + delegate class, no
  bot-specific branching (keeps it a single-responsibility orchestrator per Principle I).

### `FieldMapper` (`field_mapper.py`)

```python
class FieldMapper:
    def resolve_all(self, bot_id: str, record: TraceRecord) -> tuple[dict[str, Any], int]:
        """Returns (resolved_fields_by_name, count_of_fields_with_a_declared_path)."""

    def resolve_field(self, bot_id: str, record: TraceRecord, field: str) -> Any: ...
    def _resolve_path(self, record: TraceRecord, path: str) -> Any: ...
    def _reshape_list_items(self, bot_id: str, field: str, raw_list: list, item_schema: type) -> list: ...
```

- `_resolve_path`: splits `path` on `.`, first segment selects `record.input` / `record.output` /
  `record.metadata`; remaining segments walk nested dict keys or (if the segment parses as `int`)
  list indices. Returns a sentinel "absent" (not found: `KeyError`/`IndexError`/`TypeError` during
  traversal) vs. a resolved value (found, possibly `None` itself if the JSON literally had `null`
  there — still "found").
- Absent → field's defined empty value (FR-004); no error.
- Found but wrong type for a list-typed field (`context`, `tools_called`, `messages` expect
  `list`) → `FieldMappingTypeError(bot_id, field, path, type(resolved))` (FR-004, Decision 6).
- For `tools_called`/`messages`: once the raw list itself resolves correctly, each item is
  reshaped via `_reshape_list_items` using the declared `tools_called_item`/`messages_item`
  sub-mapping, or the Decision 4 default same-name lookup when the sub-block is absent.

### `UnmappedBotError` / `FieldMappingTypeError` (`errors.py`)

Project-local exceptions, following the `ConfigError`/`InvalidBotTypeError` convention (message
carries every diagnostic field so `except`-ing callers never need to reformat):

```python
class UnmappedBotError(ValueError):
    def __init__(self, bot_id: str) -> None: ...  # message includes bot_id

class FieldMappingTypeError(TypeError):
    def __init__(self, bot_id: str, field: str, path: str, resolved_type: type) -> None: ...
```

### `ValidationResult` (dataclass, `validation/result.py`)

| Field | Type |
|-------|------|
| `is_valid` | `bool` |
| `missing_fields` | `list[str]` (empty when `is_valid`) |

### `ValidationRuleBase` (ABC, `validation/rule_base.py`)

```python
class ValidationRuleBase(ABC):
    @abstractmethod
    def required_fields(self) -> list[str]: ...

    def validate(self, trace: NormalizedTrace) -> ValidationResult:
        """Checks each required_fields() name against trace for presence/non-emptiness."""
```

`validate()` is concrete and shared — it never raises (FR-006), reports every missing/empty
required field by name (FR-007), and is the same for every bot type; only `required_fields()`
varies per subclass (Principle VI — Strategy pattern, same shape as `EvaluationStrategyBase`).

### Concrete rules (`validation/rules/*.py`)

| Class | `required_fields()` |
|-------|---|
| `RagValidationRule` | `["input", "output", "context", "expected_output"]` |
| `AgentValidationRule` | `["input", "output", "tools_called"]` |
| `ConversationValidationRule` | `["messages"]` |

### `ValidationRule` (registry facade, `validation/rule_registry.py`)

```python
class ValidationRule:
    _REGISTRY: dict[BotType, ValidationRuleBase] = {
        BotType.RAG: RagValidationRule(),
        BotType.AGENT: AgentValidationRule(),
        BotType.CONVERSATION: ConversationValidationRule(),
    }

    @classmethod
    def check(cls, trace: NormalizedTrace, bot_type: BotType | str) -> ValidationResult: ...
```

Public entry point matching FR-006's contract ("accept a `NormalizedTrace` and a `BotType`");
mirrors `StrategyFactory.create()`'s registry-dict shape exactly (FR-008, Decision 7). Adding a
4th `BotType`'s rule is one new subclass + one registry entry — zero edits to existing rule
classes, `TraceNormalizer`, or `FieldMapper`.

## `bots.yaml` Schema Addition

See [research.md](research.md) Decision 1 for the full annotated example. Summary of new keys
under each `bots.<bot_id>` entry:

| Key | Required | Meaning |
|-----|----------|---------|
| `field_mapping.input` | optional | dot-path rooted at `input`/`output`/`metadata` |
| `field_mapping.output` | optional | same |
| `field_mapping.context` | optional | same (expects list at resolved path) |
| `field_mapping.expected_output` | optional | same |
| `field_mapping.tools_called` | optional | same (expects list at resolved path) |
| `field_mapping.tools_called_item.{name,input_parameters,output}` | optional | per-item relative key lookup override |
| `field_mapping.messages` | optional | same (expects list at resolved path) |
| `field_mapping.messages_item.{role,content}` | optional | per-item relative key lookup override |

At least one `field_mapping.*` leaf must be present per bot, or `TraceNormalizer.normalize()`
raises `UnmappedBotError` (FR-005, Decision 3).

## State / Control Flow (no state transitions — pure functions over immutable inputs)

```
TraceRecord ──▶ TraceNormalizer.normalize() ──▶ NormalizedTrace ──▶ ValidationRule.check(trace, bot_type) ──▶ ValidationResult
                        │
                        ▼
                  FieldMapper.resolve_all()
                        │
              ┌─────────┴─────────┐
       field present          field absent
              │                    │
      right type?             empty default
       │        │
      yes       no
       │        │
    value   FieldMappingTypeError
```

# Phase 1 Data Model: Synthetic Dataset Generator (M4.1)

## Configuration models

### `PersonaScenario`

| Field | Type | Notes |
|---|---|---|
| `name` | `str` | Stable scenario identifier within a persona |
| `expected_outcome` | `str` | Passed to `ConversationalGolden.expected_outcome` |

### `Persona`

| Field | Type | Notes |
|---|---|---|
| `name` | `str` | Unique persona identifier and persisted association |
| `profile` | `str` | User description for conversation simulation |
| `styling_scenario` | `str \| None` | Single-turn styling text, forwarded unchanged to `StylingConfig.scenario` |
| `task` | `str \| None` | Forwarded unchanged to `StylingConfig.task` |
| `input_format` | `str \| None` | Forwarded unchanged to `StylingConfig.input_format` |
| `expected_output_format` | `str \| None` | Forwarded unchanged to `StylingConfig.expected_output_format` |
| `scenarios` | `list[PersonaScenario]` | Named multi-turn use cases with expected outcomes, required when multi-turn generation is enabled |

`Persona` has two structurally distinct "scenario" concepts, kept under different field names to
avoid confusion: `styling_scenario` is free-text phrasing forwarded as-is into
`StylingConfig.scenario` for single-turn golden generation (FR-002/FR-003), while `scenarios` is a
list of named `PersonaScenario` entries — each with its own `expected_outcome` — used to drive
multi-turn conversation simulation (FR-005). They are independent settings; a persona may define
either, both, or neither.

`PersonaConfigResolver` reconstructs these values from `config/personas.yaml` exclusively through
`ConfigManager` and raises `PersonaConfigError` for missing/invalid requested personas.

## Authentication models

### `AuthenticatedPrincipal`

| Field | Type | Notes |
|---|---|---|
| `user_id` | `UUID` | Validated Supabase Auth JWT subject |
| `org_id` | `UUID` | Derived only from validated `app_metadata.org_id` |
| `access_token` | `str` | Kept in memory for the request scope; never logged/persisted |
| `supabase_client` | `Client` | User-scoped client carrying the JWT so RLS applies |

`OrganizationAuthorizer.authorize(access_token) -> AuthenticatedPrincipal` uses credentials from
`ConfigManager`. Invalid/expired JWT, missing subject, missing/malformed organization metadata, or
client setup failure raises `AuthorizationError`. No public operation accepts `org_id`.

## Generation classes

| Class | Responsibility |
|---|---|
| `GoldenGenerator` | Native-loader validation, structured failures, exact per-document `divmod` allocation, one native generation call per valid document, exact-count enforcement, and persona association |
| `ConversationGenerator` | Stable scenario distribution, native simulation, normalized turns, completion callback/metadata capture, and explicit ending status |
| `BotInvokerBase` | Callback strategy returning normalized `Turn`; failures become structured `[BOT_UNREACHABLE]` turns |
| `FlowiseBotInvoker` | HTTP invocation; extracts non-empty string `text` from common Flowise JSON response |
| `LangChainBotInvoker` | Native `.invoke()`; extracts `str`, `BaseMessage.content`, or dict `output`/`text`/`answer` |
| `BotInvokerFactory` | Imports and validates `bots.<id>.invocation.invoker_class`; no fixed registry |
| `SyntheticDatasetGenerator` | Authenticated facade for generation, retrieval, search, retry, and export |

`GoldenGenerator` raises `EmptyKnowledgeBaseError` when no valid documents remain and
`InsufficientGoldenCoverageError` when the target is below valid-document count or native generation
underproduces an allocation. No partial shortfall is returned or persisted.

### Conversation ending status

`ConversationRecord.ending_status` is one of:

| Value | Extraction rule |
|---|---|
| `expected_outcome_reached` | Completion callback or native test-case metadata explicitly reports expected-outcome success |
| `natural_conclusion` | Completion callback/native metadata explicitly reports natural completion without expected-outcome success |
| `max_turn_incomplete` | No successful completion signal and max user simulations were consumed; also the safe fallback for ambiguous unfinished output |
| `bot_failure` | Any normalized assistant turn contains `[BOT_UNREACHABLE]`; structured error is copied to `bot_error` |

Precedence is `bot_failure`, explicit expected outcome, explicit natural conclusion, then max-turn
incomplete. This avoids inferring success from transcript length.

## Persistence and result models

### `DocumentFailure`

| Field | Type | Notes |
|---|---|---|
| `path` | `str` | Source path relative to configured docs root where feasible |
| `stage` | `Literal["readability", "parsing"]` | Failure boundary |
| `error_type` | `str` | Stable exception/error category |
| `message` | `str` | Sanitized diagnostic, no credentials |

### `SyntheticDataset`

| Field | Type | Notes |
|---|---|---|
| `id` | `UUID` | New per generation run |
| `bot_id` | `str` | Configured bot identifier |
| `org_id` | `UUID \| None` | Principal org for normal writes; SQL remains nullable |
| `personas` | `list[str]` | Included persona names |
| `source_documents` | `list[str]` | Valid documents that contributed |
| `document_failures` | `list[DocumentFailure]` | Persisted and exported unreadable/parser failures |
| `indexing_status` | `Literal["pending", "indexed", "failed"]` | Complete-dataset semantic index state; spec.md's "indexing-failed status" wording refers to the literal value `"failed"` |
| `created_at` | `datetime` | UTC timestamp |
| `goldens` | `list[GoldenRecord]` | Exact configured count per persona |
| `conversations` | `list[ConversationRecord]` | Generated multi-turn cases |

### `GoldenRecord`

| Field | Type | Notes |
|---|---|---|
| `id` | `UUID` | Source record ID for vector metadata |
| `dataset_id` | `UUID` | Parent FK |
| `org_id` | `UUID \| None` | Copied from parent; mismatch rejected in database |
| `persona_name` | `str` | Preserves style/persona association |
| `input` | `str` | Native golden input |
| `expected_output` | `str \| None` | Native expected output |
| `context` | `list[str]` | Native context |
| `source_file` | `str` | Valid contributing document |

### `ConversationRecord`

Implements spec.md's "Simulated Conversation" key entity.

| Field | Type | Notes |
|---|---|---|
| `id` | `UUID` | Source record ID for vector metadata |
| `dataset_id` | `UUID` | Parent FK |
| `org_id` | `UUID \| None` | Copied from parent; mismatch rejected in database |
| `persona_name` | `str` | Persona association |
| `scenario_name` | `str` | Scenario association |
| `turns` | `list[dict]` | Normalized ordered role/content plus safe metadata |
| `ending_status` | `ConversationEndingStatus` | Explicit extraction rules above |
| `bot_error` | `dict \| None` | Structured invoker error for `bot_failure` |

### `SearchResult`

| Field | Type | Notes |
|---|---|---|
| `content_type` | `Literal["golden", "conversation"]` | Normalized source type |
| `source_record_id` | `UUID` | Golden/conversation ID |
| `dataset_id` | `UUID` | Parent dataset |
| `persona_name` | `str` | Shared metadata |
| `text` | `str` | Indexed normalized content |
| `score` | `float` | Similarity score |
| `metadata` | `dict` | Type-specific source/scenario metadata |

## Repository and exporters

`DatasetRepository` is persistence-only. Its internal authenticated operations are `save(dataset,
principal)`, `get_by_id(dataset_id, principal)`, `get_by_bot(bot_id, principal)`,
`search_content(query, principal, k)`, and `retry_indexing(dataset_id, principal)`. It uses
`principal.supabase_client` and applies principal-org filters in addition to RLS. It has no JSON/CSV
methods.

`DatasetExporterBase.export(dataset, output_dir) -> Path` is implemented by
`JsonDatasetExporter` and `CsvDatasetExporter`. `DatasetExporterFactory` imports the dotted class
from `synthetic.exporters.<format>` and validates the base class. Both formats include
`document_failures` as well as goldens and conversations.

## Configuration schema

```yaml
# config/settings.yaml
synthetic:
  docs_dir: "data/synthetic/docs"
  output_dir: "data/synthetic/output"
  goldens_per_persona: 10
  conversations_per_persona: 6
  max_conversation_turns: 15
  exporters:
    json: "deepeval_platform.synthetic.json_dataset_exporter.JsonDatasetExporter"
    csv: "deepeval_platform.synthetic.csv_dataset_exporter.CsvDatasetExporter"
```

```yaml
# config/bots.yaml additions
bots:
  test_rag_bot:
    platform: flowise
    invocation:
      invoker_class: "deepeval_platform.synthetic.flowise_bot_invoker.FlowiseBotInvoker"
      endpoint_url: "https://flowise.internal/api/v1/prediction/<chatflow-id>"
  test_agent_bot:
    platform: langchain
    invocation:
      invoker_class: "deepeval_platform.synthetic.langchain_bot_invoker.LangChainBotInvoker"
      chain_target: "my_bots.agent_bot.graph"
```

```dotenv
# .env.example planned addition; credentials only
SUPABASE_ANON_KEY=
```

## Migration design

```sql
CREATE TABLE synthetic_datasets (
    id UUID PRIMARY KEY,
    bot_id TEXT NOT NULL,
    org_id UUID,
    personas JSONB NOT NULL DEFAULT '[]',
    source_documents JSONB NOT NULL DEFAULT '[]',
    document_failures JSONB NOT NULL DEFAULT '[]',
    indexing_status TEXT NOT NULL DEFAULT 'pending',
    created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE synthetic_goldens (
    id UUID PRIMARY KEY,
    dataset_id UUID NOT NULL REFERENCES synthetic_datasets(id) ON DELETE CASCADE,
    org_id UUID,
    persona_name TEXT NOT NULL,
    input TEXT NOT NULL,
    expected_output TEXT,
    context JSONB NOT NULL DEFAULT '[]',
    source_file TEXT NOT NULL
);

CREATE TABLE synthetic_conversations (
    id UUID PRIMARY KEY,
    dataset_id UUID NOT NULL REFERENCES synthetic_datasets(id) ON DELETE CASCADE,
    org_id UUID,
    persona_name TEXT NOT NULL,
    scenario_name TEXT NOT NULL,
    turns JSONB NOT NULL DEFAULT '[]',
    ending_status TEXT NOT NULL,
    bot_error JSONB
);
```

The migration also:
- enables RLS on all three tables;
- adds `SELECT`, `INSERT`, and `UPDATE` policies using
  `(auth.jwt()->'app_metadata'->>'org_id')::uuid = org_id`, with equivalent `WITH CHECK` clauses.
  No `DELETE` policy is added: the repository exposes no delete method, so child-row cleanup
  relies solely on `ON DELETE CASCADE` from a parent `synthetic_datasets` deletion performed
  outside application scope (e.g. direct admin/DB access);
- adds a trigger for each child table that loads the parent and sets `NEW.org_id = parent.org_id`,
  rejecting an explicitly different value;
- indexes `org_id`, parent FKs, bot ID, and indexing status as needed.

The columns remain nullable for constitution compatibility, but authenticated policies do not grant
access to null-org rows.

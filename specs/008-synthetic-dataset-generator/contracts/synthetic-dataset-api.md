# Contract: Synthetic Dataset Generator API Surface (M4.1)

This is an authenticated Python service boundary. It does not define an HTTP route, but every public
data operation accepts a Supabase Auth access token and resolves a trusted principal before work.
There is no public `org_id` parameter.

## Public facade

```python
from deepeval_platform.synthetic.synthetic_dataset_generator import SyntheticDatasetGenerator

service = SyntheticDatasetGenerator()

dataset = service.generate(
    access_token=user_access_token,
    bot_id="test_rag_bot",
    persona_names=None,  # optional subset of configured personas; None/omitted selects all
)

fetched = service.get_dataset(access_token=user_access_token, dataset_id=dataset.id)
history = service.list_datasets(access_token=user_access_token, bot_id="test_rag_bot")
hits = service.search_content(
    access_token=user_access_token,
    query="password reset conversation",
    k=5,
)  # list[SearchResult], covering goldens and conversations

service.retry_indexing(access_token=user_access_token, dataset_id=dataset.id)
json_path = service.export_dataset(
    access_token=user_access_token,
    dataset_id=dataset.id,
    format="json",
)
```

Every method first calls `OrganizationAuthorizer.authorize(access_token)`. Invalid/expired tokens or
missing/malformed trusted `app_metadata.org_id` raise `AuthorizationError`. The facade passes the
resulting `AuthenticatedPrincipal` to the repository, which uses its JWT-scoped client so RLS
applies. Callers cannot select or override an organization.

`generate` raises:
- `PersonaConfigError` for missing/invalid personas;
- `EmptyKnowledgeBaseError` when single-turn generation finds no readable parser-valid document;
- `InsufficientGoldenCoverageError` when the exact target is below valid-document count or native
  generation cannot meet an assigned document count;
- `AuthorizationError` before generation for invalid authenticated context.

Unreadable/parser-invalid documents do not abort when at least one valid document remains. They are
returned and persisted as `dataset.document_failures` and included in JSON/CSV. A native golden
shortfall is not treated as a partial success: the run raises and is not persisted.

## Internal generation contracts

```python
goldens, document_failures = GoldenGenerator(judge_model=judge).generate(
    persona=persona,
    document_paths=document_paths,
    goldens_per_persona=10,
)

conversations = ConversationGenerator(judge_model=judge, invoker=invoker).generate(
    persona=persona,
    conversations_per_persona=6,
    max_turns=15,
)
```

Golden generation validates native loaders and calls the native synthesizer per document. All four
configured styling fields are forwarded unchanged and each record retains `persona_name`.
Conversation records use one of `expected_outcome_reached`, `natural_conclusion`,
`max_turn_incomplete`, or `bot_failure` according to callback/native metadata rules.

## Bot invoker extension

```python
invoker = BotInvokerFactory.create(bot_id="test_rag_bot")
turn = invoker(input="How do I reset my password?", turns=[], thread_id="conv-1")
```

The factory reads `bots.test_rag_bot.invocation.invoker_class` through `ConfigManager`, imports the
dotted class, validates a concrete `BotInvokerBase` subclass, and instantiates it. It contains no
factory dictionary or platform switch. A new bot invocation type requires only a subclass and bot
configuration.

Flowise success requires a JSON object with a non-empty string `text`. LangChain success accepts a
string, `BaseMessage.content`, or dict `output`/`text`/`answer`. Malformed or failed calls return:

```python
Turn(
    role="assistant",
    content="[BOT_UNREACHABLE]",
    metadata={
        "error": {
            "code": "malformed_response",
            "type": "ResponseNormalizationError",
            "message": "...sanitized...",
            "bot_id": "test_rag_bot",
        }
    },
)
```

## Persistence contract

```python
principal = authorizer.authorize(user_access_token)
dataset_id = repository.save(dataset, principal=principal)
dataset = repository.get_by_id(dataset_id, principal=principal)
datasets = repository.get_by_bot("test_rag_bot", principal=principal)
hits = repository.search_content("password reset", principal=principal, k=5)
repository.retry_indexing(dataset_id, principal=principal)
```

Repository methods are internal collaborators of the authenticated facade. They accept
`AuthenticatedPrincipal`, not raw `org_id` or `access_token`, and have no export methods.

The `synthetic_content` collection includes both goldens and conversations. Every returned
`SearchResult` has `content_type`, `source_record_id`, `dataset_id`, `persona_name`, normalized
`text`, score, and metadata. Search returns content only for Supabase-authorized datasets whose
indexing status is `indexed`.

If any Qdrant write fails, the repository deletes every point for that dataset, records `failed`,
and does not expose partial content. Retry rebuilds the whole dataset index and changes the status
to `indexed` only after complete success.

## Export extension

```python
exporter = DatasetExporterFactory.create("csv")
path = exporter.export(dataset, output_dir)
```

The public `export_dataset` method authenticates and retrieves the aggregate before creating the
configured exporter. `DatasetExporterFactory` resolves `synthetic.exporters.<format>` through
`ConfigManager` and validates `DatasetExporterBase`. JSON and CSV include metadata, goldens,
conversations, and document failures. A new target requires only a subclass and one config entry.

# Quickstart: Validating the Synthetic Dataset Generator (M4.1)

## Prerequisites

- Constitution v1.4.0 has landed with explicit approval for `pypdf`, `docx2txt`, and `chromadb`;
  then `uv sync` installs them from `pyproject.toml`.
- The LangChain MCP consultation required by T000 is recorded in research.md. Official web
  documentation alone does not satisfy this gate.
- `config/settings.yaml` defines `synthetic.docs_dir`, `synthetic.output_dir`,
  `synthetic.goldens_per_persona`, `synthetic.conversations_per_persona`,
  `synthetic.max_conversation_turns`, and JSON/CSV exporter dotted classes.
- `config/personas.yaml` contains at least one persona.
- Each generated-against bot defines `bots.<id>.invocation.invoker_class`; Flowise also defines
  `endpoint_url`, and LangChain defines `chain_target`.
- `.env` contains credentials only. `SUPABASE_URL` and the planned `SUPABASE_ANON_KEY` are needed
  for authenticated user-scoped access; no synthetic paths or thresholds belong in `.env`.
- Supabase test users have trusted `app_metadata.org_id`, and
  `migrations/002_synthetic_datasets.sql` is applied for storage integration tests.

## Strict TDD workflow

For each behavior, add its unit or integration test and run that test before production code. It
must fail for the intended reason (RED). Add the minimum implementation (GREEN), then refactor while
the same test remains green. Merely creating test files does not satisfy this gate.

```bash
uv run pytest tests/unit/config/test_synthetic_config.py -v
uv run pytest tests/unit/synthetic -v
uv run pytest tests/unit/repositories/test_dataset_repository.py -v
uv run pytest tests/unit/repositories/test_synthetic_migration.py -v
uv run pytest tests/integration/test_synthetic_document_loaders_integration.py -v -m integration
uv run pytest tests/integration/test_flowise_bot_invoker_integration.py -v -m integration
uv run pytest tests/integration/test_synthetic_storage_integration.py -v -m integration
uv run pytest tests/integration/test_synthetic_generation_flow_integration.py -v -m integration
uv run pytest --cov=deepeval_platform --cov-report=term-missing --cov-fail-under=80
```

Supabase/Qdrant integration tests are marked `integration` and skip with an explicit reason when
their dedicated test environment variables are absent. Loader and local HTTP integration tests run
without service credentials. Skipped service tests remain a reported integration gap; an optional
manual run is not a substitute.

## Automated coverage

| Requirement | Automated test scope |
|---|---|
| Real PDF/Markdown/DOCX loading | Build small real fixtures and execute native loaders; stub only the LLM/native generation seam as far downstream as feasible |
| Exact golden target and document coverage | Target below valid-doc count raises; stable `divmod` allocation; each document contributes; overproduction truncates; underproduction raises without persistence |
| Parser/read failures | Corrupt/unreadable fixture becomes structured `DocumentFailure`; valid files continue; JSON/CSV contain failures |
| Styling | Assert every configured `StylingConfig` field is forwarded unchanged and every output retains persona association |
| Conversation endings | Separate tests for expected outcome, natural conclusion, max-turn incomplete, and bot failure; one failed attempt must not prevent remaining persona/scenario attempts |
| Flowise boundary | Local HTTP server verifies request payload/session and `text` extraction; malformed/non-2xx response yields structured marker |
| LangChain normalization | Unit tests cover `str`, `BaseMessage.content`, dict `output`/`text`/`answer`, malformed forms, and structured marker |
| Bot extension | Dotted-class import/base validation; custom test subclass loads solely from config, with no factory edit |
| Authentication | Invalid/expired/missing-org JWT raises; trusted `app_metadata.org_id` becomes principal; caller cannot pass org ID |
| RLS and persistence | Environment-backed Supabase tests prove same-org access, cross-org denial, child org inheritance, and mismatch rejection |
| Semantic content | Qdrant test indexes/searches both goldens and conversations, returns normalized `SearchResult`, and uses a controlled corpus proving a known relevant result ranks in the first three for each content type |
| Failed indexing | Inject mid-index failure, assert all dataset points removed/status failed/search excluded, then retry whole aggregate |
| Export extension | Facade authenticates/retrieves then delegates; JSON/CSV include all records/failures; custom exporter loads solely from config |
| Full primary flow | With stubbed LLM and local bot plus test Supabase/Qdrant, generate -> persist -> create a fresh service/repository -> retrieve and search; inject one bot failure and prove remaining attempts continue and its structured error survives retrieval/exports |

Unit tests continue to mock external LLM, bot, Supabase, and Qdrant boundaries for deterministic
class-level behavior. They complement rather than replace the integration suite.

## Authenticated smoke example

```python
from deepeval_platform.synthetic.synthetic_dataset_generator import SyntheticDatasetGenerator

service = SyntheticDatasetGenerator()
dataset = service.generate(access_token=user_access_token, bot_id="test_rag_bot")
reloaded = service.get_dataset(access_token=user_access_token, dataset_id=dataset.id)
hits = service.search_content(access_token=user_access_token, query="reset instructions", k=5)
csv_path = service.export_dataset(
    access_token=user_access_token,
    dataset_id=dataset.id,
    format="csv",
)
```

Confirm the count is exactly `synthetic.goldens_per_persona` for every persona, every valid source
appears in at least one golden, failures appear in `document_failures`, search can return both
content types, and all calls fail with another organization's authenticated token. This smoke check
is diagnostic only and does not satisfy the automated integration gate.

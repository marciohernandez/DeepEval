# Phase 0 Research: Synthetic Dataset Generator (M4.1)

## R1. Configuration remains centralized

`ConfigManager` flattens YAML into dotted keys and is the sole configuration reader. Existing
index-probing can reconstruct persona/scenario lists without adding direct YAML access.

**Decision**: use `ConfigManager` for all configuration. Paths and thresholds live in
`config/settings.yaml` as `synthetic.docs_dir`, `synthetic.output_dir`,
`synthetic.goldens_per_persona`, `synthetic.conversations_per_persona`, and
`synthetic.max_conversation_turns`. Export classes use
`synthetic.exporters.<format>`. Credentials alone remain in `.env`; add `SUPABASE_ANON_KEY` to the
planned `.env.example` update. No `SYNTHETIC_*` environment variables are introduced.

## R2. Native DeepEval generation and completion hooks

DeepEval's official Golden Synthesizer documentation was consulted on 2026-07-15:
`https://deepeval.com/docs/synthesizer-introduction` (redirecting to the current Golden
Synthesizer documentation). It confirms native document generation, `StylingConfig`, supported
document formats, and the separate `ConversationSimulator` responsibility. Installed-package
signatures were then checked against `deepeval==4.0.7`.

Installed `deepeval==4.0.7` exposes `Synthesizer(styling_config=...)`,
`generate_goldens_from_docs(document_paths, max_goldens_per_context=...)`, and
`ConversationSimulator.simulate(..., max_user_simulations=..., on_simulation_complete=...)`.
`StylingConfig` is constructor-bound, so each persona needs its own `Synthesizer`. DeepEval invokes
the model callback with supported members of `input`, `turns`, and `thread_id`, and expects the
callback result to be a `Turn`.

**Decision**: use one native synthesizer per persona and the native simulator/default expected-
outcome controller. Deterministic style validation means tests assert that all configured
`scenario`, `task`, `input_format`, and `expected_output_format` values are passed unchanged into
`StylingConfig`, and every resulting record preserves the originating `persona_name`. It does not
attempt nondeterministic prose comparison.

Completion extraction is explicit. The generator records completion details supplied to
`on_simulation_complete`; then it reads native test-case completion/stopping metadata when present.
An explicit native expected-outcome result maps to `expected_outcome_reached`; an explicit natural
completion maps to `natural_conclusion`; a `[BOT_UNREACHABLE]` turn maps to `bot_failure`; and an
otherwise unfinished case at `max_user_simulations` maps to `max_turn_incomplete`. Ambiguous cases
remain `max_turn_incomplete`, never guessed successful. Tests cover all four statuses.

## R3. Document loading dependencies are constitution-approved

DeepEval's chunker lazily uses LangChain community `PyPDFLoader`, `TextLoader`, and
`Docx2txtLoader`; `pypdf`, `docx2txt`, and `chromadb` are needed at runtime.

**Decision**: add all three dependencies. Constitution v1.4.0 explicitly approves them. This is not
an exemption from amendment governance; implementation waits for that amendment to land. Parsing
continues through the native loader boundary rather than project-authored PDF/DOCX parsers.

## R4. Exact count and document coverage require per-document generation

`max_goldens_per_context` is not a total and one batch call cannot isolate a parser failure or prove
one output per document.

**Decision**: discover supported files in stable path order and validate each through the native
loader boundary. Persist one `DocumentFailure(path, stage, error_type, message)` for every
unreadable or parser-invalid file. If no valid files remain, raise `EmptyKnowledgeBaseError`. If
`goldens_per_persona < len(valid_documents)`, raise `InsufficientGoldenCoverageError` before LLM
generation.

For each persona, calculate `base, remainder = divmod(target, len(valid_documents))`; assign
`base + 1` to the first `remainder` documents and `base` to the rest. Call native generation once
per document. Truncate stable overproduction to that document's allocation. If any valid document
underproduces, raise `InsufficientGoldenCoverageError` with document, requested, and produced
counts. Do not persist or report a partial persona. This produces exactly the configured total and
guarantees every valid document contributes at least one golden while isolating parser failures.

## R5. Conversation distribution

`ConversationSimulator` returns one test case per repeated `ConversationalGolden` input.

**Decision**: distribute `synthetic.conversations_per_persona` across a persona's scenarios using
stable `divmod`; pass `synthetic.max_conversation_turns` directly as `max_user_simulations`.

## R6. Bot invocation is config-extensible and normalized

The mandatory LangChain MCP consultation was completed on 2026-07-15 via the `claude.ai Langchain
1.0` MCP server (`search_docs_by_lang_chain` and `query_docs_filesystem_docs_by_lang_chain` tools),
now available in this workspace (it was not present when `opencode mcp list` was checked earlier the
same day). The server's `/oss/python/langchain/models.mdx` page, under "Invocation" > "Invoke",
confirms the native `.invoke()` contract: calling `model.invoke(...)` with a string or a list of
messages returns an `AIMessage` — a `BaseMessage` subclass — whose textual result is read from the
`.content` attribute (e.g. `AIMessage("J'adore la programmation.")`). This matches, via the
MCP-served documentation rather than the earlier web-only check, the contract already assumed below
for `LangChainBotInvoker`. The constitution-mandated MCP consultation is satisfied; implementation is
no longer blocked on this principle.

A fixed platform dictionary violates the requirement that a new bot type need only a subclass and
configuration.

**Decision**: `BotInvokerFactory` reads `bots.<id>.invocation.invoker_class`, imports the dotted
class, verifies it is a concrete `BotInvokerBase` subclass, and instantiates it with config-derived
bot options. Existing Flowise and LangChain bot configs name `FlowiseBotInvoker` and
`LangChainBotInvoker`; `platform` may remain descriptive but does not select the class.

`FlowiseBotInvoker` posts the standard question/session payload and accepts a decoded JSON object
whose common response `text` field is a non-empty string. `LangChainBotInvoker` accepts a returned
`str`, `BaseMessage.content` string, or dict with the first non-empty string among `output`, `text`,
and `answer`. Both normalize success to `Turn(role="assistant", content=text, metadata={...})`.
Unexpected status, decoding failure, absent/unsupported content, or invocation exception yields
`Turn(content="[BOT_UNREACHABLE]", metadata={"error": {"code": ..., "type": ...,
"message": ..., "bot_id": ...}})`. Error metadata is structured and sanitized; invokers do not
raise through the simulator callback.

## R7. Authentication and RLS are part of this feature boundary

Caller-supplied `org_id` cannot establish organization membership. Supabase supports JWT validation,
user-scoped clients, and Postgres RLS.

**Decision**: every public operation accepts `access_token`. `OrganizationAuthorizer` uses
`SUPABASE_URL` and `SUPABASE_ANON_KEY` through `ConfigManager`, validates the token with Supabase
Auth, requires a subject and a valid UUID in trusted `user.app_metadata.org_id`, and returns
`AuthenticatedPrincipal(user_id, org_id, access_token, supabase_client)`. Invalid, expired, or
unscoped tokens raise `AuthorizationError`. The returned client carries the user's JWT; repository
queries use only that client and principal. There is no service/repository API accepting raw
`org_id`, and no service-role client on public request paths.

All three tables include nullable `org_id`. Child inserts copy the aggregate parent's `org_id`;
database trigger/check logic rejects mismatches. RLS policies compare row `org_id` with the UUID in
`auth.jwt()->'app_metadata'->>'org_id'`, including `WITH CHECK` on writes. Nullable supports schema
readiness, not anonymous access: null-org rows are denied by these policies.

## R8. Persistence and aggregate-wide semantic indexing

The relational aggregate uses `synthetic_datasets`, `synthetic_goldens`, and
`synthetic_conversations`. `synthetic_datasets.document_failures` stores structured parser/read
failures so exports and later retrieval preserve them.

**Decision**: index both goldens and conversations into one `synthetic_content` collection. Golden
text combines input, expected output, and context. Conversation text serializes normalized turn
role/content in order. Every point includes `content_type` (`golden` or `conversation`),
`source_record_id`, `dataset_id`, `org_id`, and persona/type metadata. `search_content` returns a
normalized `SearchResult`, not persistence records.

Supabase is saved first. Qdrant indexing is complete-dataset work. On any point failure, delete all
points filtered by `dataset_id`, mark the dataset `failed`, and exclude it from search. Search also
authorizes the dataset IDs against Supabase before returning points. `retry_indexing` reloads the
whole authorized aggregate and attempts all content again; only a complete successful write marks
it `indexed`.

## R9. Export is a strategy, not repository behavior

JSON/CSV formatting is not a storage query and repository methods per format create a closed
registry that must change for every target.

**Decision**: `DatasetExporterBase.export(dataset, output_dir) -> Path` has
`JsonDatasetExporter` and `CsvDatasetExporter` implementations. `DatasetExporterFactory` reads
`synthetic.exporters.<format>`, imports and validates the dotted subclass, and instantiates it. The
public facade authenticates, retrieves the dataset, resolves `synthetic.output_dir`, and delegates.
Both formats include dataset metadata, goldens, conversations, and `DocumentFailure` records. A new
target requires only a subclass and config entry.

## R10. Integration testing is automated

**Decision**: unit tests mock external boundaries, but the integration gate additionally runs real
PDF/Markdown/DOCX loaders against generated fixtures while stubbing only the LLM/generation seam;
a local HTTP server exercises Flowise request/response parsing; marked integration tests exercise
Supabase Auth/RLS and Qdrant when their environment credentials are present; and a full flow covers
generation, persistence, and fresh retrieval. Missing service credentials cause an explicit pytest
skip, not a pass claim. Optional manual checks are diagnostic only.

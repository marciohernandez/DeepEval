# Feature Specification: Synthetic Dataset Generator

**Feature Branch**: `008-synthetic-dataset-generator`

**Created**: 2026-07-15

**Status**: Draft

**Input**: User description: "Módulos em escopo para M4.1 — SyntheticDatasetGenerator: SyntheticDatasetGenerator orquestra a geração lendo personas via ConfigManager e gerando goldens e conversas por persona; geração single-turn via Synthesizer.generate_goldens_from_docs() com StylingConfig moldado a cada persona a partir de documentos de config/knowledge_base/ (PDF, MD, DOCX); geração multi-turn via ConversationSimulator com ConversationalGolden por persona × cenário, com model_callback chamando o bot real (Flowise via HTTP, LangChain/LangGraph via invoke); DatasetRepository persiste e recupera datasets (Supabase para metadados/histórico, Qdrant para embeddings/busca semântica, JSON/CSV local); configuração via .env: SYNTHETIC_DOCS_DIR, SYNTHETIC_OUTPUT_DIR, SYNTHETIC_GOLDENS_PER_PERSONA, SYNTHETIC_CONVERSATIONS_PER_PERSONA."

## Clarifications

### Session 2026-07-15

- Q: How should a simulated conversation end if the expected outcome is not reached and the bot does not naturally conclude? → A: Stop at a configurable maximum turn count; retain the transcript marked incomplete.
- Q: What should happen if Supabase persistence succeeds but Qdrant semantic indexing fails? → A: Retain the dataset with an indexing-failed status, exclude it from semantic search, and allow indexing retry.
- Q: When a persona has multiple scenarios, how should its configured conversation count be allocated? → A: Treat it as the persona's total and distribute conversations as evenly as possible across scenarios.
- Q: Which local export formats must the feature support? → A: Both JSON and CSV.
- Q: Who may generate, retrieve, search, and export synthetic datasets? → A: Any authenticated member of the dataset's organization.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Generate single-turn evaluation goldens from company documents (Priority: P1)

An evaluation engineer needs a baseline set of question/expected-answer pairs to evaluate a bot's
knowledge, without hand-writing them. They point the system at the company's knowledge base
documents (FAQs, contracts, manuals) and, for each configured user persona, receive a set of
goldens styled to match how that persona would actually ask questions and expect answers.

**Why this priority**: This is the foundation of the whole feature — without goldens grounded in
real company knowledge, there is no dataset to evaluate against. It delivers value standalone
(goldens can be exported and used manually even before multi-turn or persistence exist).

**Independent Test**: Can be fully tested by pointing the generator at a folder containing at
least one document, configuring one persona, running generation, and verifying that a
non-empty set of goldens is produced, each with an input and expected output styled to that
persona.

**Acceptance Scenarios**:

1. **Given** a knowledge base folder containing PDF, Markdown, and DOCX documents and one
   configured persona, **When** the engineer requests single-turn goldens for that persona,
   **Then** the system returns a set of goldens (input + expected output) whose scenario, task,
   and phrasing style reflect that persona's profile.
2. **Given** two personas with different profiles (e.g. "IT Manager" and "Dissatisfied
   Customer") configured against the same documents, **When** goldens are generated for both,
   **Then** every configured styling field is applied to the corresponding generation request,
   every returned golden retains its persona association, and the two resulting sets carry
   different scenario, task, or format instructions according to those persona profiles.
3. **Given** the configured goldens-per-persona target, **When** generation completes,
   **Then** the number of goldens produced for each persona matches the configured target.
4. **Given** N readable supported documents and a configured target of at least N goldens per
   persona, **When** generation completes, **Then** every readable document contributes at least
   one golden for each persona and the final count still matches the configured target exactly.

---

### User Story 2 - Generate multi-turn conversation datasets against the real bot (Priority: P2)

An evaluation engineer needs to test how a bot behaves across an entire conversation, not just a
single question. They select a persona and a scenario (what the user is trying to accomplish and
what a successful outcome looks like), and the system drives a simulated conversation against the
actual running bot, capturing the full exchange as a reusable test case.

**Why this priority**: Builds directly on persona configuration from User Story 1 and is
necessary for evaluating conversational quality (a core product goal per the observability/
evaluation platform), but it depends on a real bot connection and is more complex to set up, so
it is delivered second.

**Independent Test**: Can be fully tested by configuring one persona with one scenario, pointing
the system at a running bot (of either supported integration type), running generation, and
verifying that a complete simulated conversation transcript is produced and tagged with the
persona and scenario it came from.

**Acceptance Scenarios**:

1. **Given** a persona with an assigned scenario and expected outcome, and a reachable bot,
   **When** the engineer requests multi-turn conversation generation, **Then** the system
   produces a simulated conversation between the persona and the bot, ending when the scenario's
   expected outcome is reached, the conversation naturally concludes, or the configured maximum
   turn count is reached.
2. **Given** a bot integrated via a web/HTTP-based platform and a bot integrated via a direct
   orchestration call, **When** multi-turn generation is run against each, **Then** both produce
   conversation records with the same normalized fields: persona, scenario, ordered role/content
   turns, expected-outcome status, incomplete status, and structured bot error, regardless of how
   the underlying bot is reached.
3. **Given** the configured conversation count target per persona, **When** generation
   completes, **Then** the total number of simulated conversations produced for each persona
   matches the configured target and is distributed as evenly as possible across that persona's
   scenarios.

---

### User Story 3 - Persist and retrieve generated datasets for reuse (Priority: P3)

An evaluation engineer who generated goldens and conversations yesterday wants to reuse that
exact dataset today to compare a new bot version against the same baseline, or to search past
datasets for similar generated content, instead of regenerating from scratch every time.

**Why this priority**: Without persistence, every generation run is thrown away after use,
which defeats the purpose of building a reusable evaluation baseline. It is ordered last because
it depends on generation (User Stories 1 and 2) already producing something worth saving.

**Independent Test**: Can be fully tested by generating a small dataset, saving it, restarting
the retrieval path independently of generation, and confirming the exact same dataset (goldens,
conversations, and their persona/scenario metadata) can be listed, fetched, and searched by
similarity.

**Acceptance Scenarios**:

1. **Given** a freshly generated set of goldens and conversations for one or more personas,
   **When** the engineer saves the dataset, **Then** the dataset's metadata and history become
   retrievable later by identifying attributes (e.g. bot, persona, generation date).
2. **Given** a previously saved dataset, **When** the engineer requests a semantic search for
   content similar to a given topic, **Then** the system returns matching goldens and conversation
   content ranked by relevance and identifies each result's content type and source dataset.
3. **Given** a previously saved dataset, **When** the engineer requests a local export,
   **Then** the system can produce either a JSON or CSV file containing the full dataset.
4. **Given** an authenticated organization member, **When** the engineer generates, retrieves,
   searches, or exports datasets, **Then** the operation is limited to datasets belonging to that
   member's organization.

---

### Edge Cases

- What happens when the configured knowledge base folder is empty or contains no supported
  document types? The system MUST fail generation for that run with a clear error rather than
  silently producing zero goldens.
- What happens when a persona is referenced by a scenario but not found in the persona
  configuration? The system MUST reject that generation request with a clear error identifying
  the missing persona.
- What happens when the real bot is unreachable or times out during multi-turn generation? The
  system MUST record the failure for that specific conversation attempt and continue with
  remaining personas/scenarios rather than aborting the entire run.
- What happens when a conversation reaches the configured maximum turn count without achieving
  its expected outcome or naturally concluding? The system MUST stop the conversation, retain its
  transcript, and mark it incomplete.
- What happens when a document in the knowledge base folder is corrupted or unreadable? The
  system MUST skip that document, add a structured document-failure record, log the failure, and
  continue generating from the remaining documents.
- What happens when the configured golden target is lower than the number of readable supported
  documents, or native generation cannot produce the exact target while covering every readable
  document? The system MUST reject the run with a clear coverage error rather than return an
  undersized or partially covered dataset.
- What happens when generation is requested for zero configured personas? The system MUST reject
  the request with a clear error, since there is nothing to style goldens or conversations for.
- What happens when the same dataset generation is run twice with identical configuration? Each
  run MUST produce a distinct, independently retrievable dataset (no silent overwrite of prior
  history).
- What happens when dataset metadata is persisted but semantic indexing fails? The system MUST
  retain the dataset with an indexing-failed status, exclude it from semantic search results,
  and allow its indexing to be retried.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST read persona definitions (profile, scenario, expected outcome) from
  the project's central configuration source before any generation runs.
- **FR-002**: System MUST generate single-turn goldens (input + expected output) from documents
  in the configured knowledge base location, supporting at minimum PDF, Markdown, and DOCX
  document formats.
- **FR-003**: System MUST style single-turn goldens per persona, so that goldens generated for
  different personas from the same source documents differ in scenario, task framing, and
  phrasing style.
- **FR-004**: System MUST generate a configurable number of goldens per persona for single-turn
  generation, using a project-level configured value (no per-run override). A successful
  run MUST return exactly that number; inability to meet it MUST fail the run with a coverage
  error rather than return a silent or logged shortfall.
- **FR-005**: System MUST generate multi-turn simulated conversations for each persona across its
  configured scenarios, producing a conversation transcript for each generated conversation.
- **FR-006**: System MUST drive multi-turn conversations against the actual bot under
  evaluation, not a mocked or stubbed response source.
- **FR-007**: System MUST support connecting to bots exposed as an HTTP-based web service as
  well as bots invoked as a direct in-process orchestration call, producing equivalent dataset
  output regardless of connection type.
- **FR-008**: System MUST generate a configurable number of simulated conversations per persona
  in total for multi-turn generation, using a project-level configured value (no per-run
  override). For a persona with multiple scenarios, the total MUST be distributed as evenly as
  possible across those scenarios.
- **FR-009**: System MUST allow the knowledge base document location and the generated dataset
  output location to be configured independently of source code (i.e., no hardcoded paths).
- **FR-010**: System MUST persist generated datasets, including their metadata (bot, persona,
  scenario, generation timestamp) and full generation history, in a way that survives beyond the
  process that generated them.
- **FR-011**: System MUST make both persisted goldens and persisted conversation content
  searchable by semantic similarity, not only by exact metadata match. Every result MUST identify
  its content type and source dataset.
- **FR-012**: System MUST support exporting the full content of a persisted dataset to both JSON
  and CSV local files.
- **FR-013**: System MUST reject a generation request when no personas are configured, or when
  a persona name selected by the request cannot be found, with an error that identifies the
  specific problem. Omitting the selection means all configured personas; an explicit selection
  MUST contain at least one valid persona name.
- **FR-014**: System MUST NOT allow a document read failure or a knowledge base parsing error to
  abort generation for the entire run; failures MUST be isolated to the specific document
  involved, logged, captured in a structured failure report, and generation MUST continue with the
  remaining documents unless exact count and coverage can no longer be satisfied.
- **FR-015**: System MUST NOT allow a single failed bot call during multi-turn generation to
  abort the entire run; the failure MUST be recorded for that specific persona/scenario
  combination and generation MUST continue with the remaining combinations.
- **FR-016**: System MUST record each generation run as a distinct, independently retrievable
  dataset rather than overwriting a prior run's persisted history.
- **FR-017**: System MUST stop a simulated conversation at a configurable maximum turn count when
  it has neither achieved its expected outcome nor naturally concluded, retaining the transcript
  and marking the conversation incomplete.
- **FR-018**: System MUST track semantic indexing status for each persisted dataset. A dataset
  whose indexing fails MUST remain retrievable by metadata, be excluded from semantic search,
  and support a later indexing retry.
- **FR-019**: System MUST require an authenticated organization member for dataset generation,
  retrieval, semantic search, export, and indexing retry, and MUST isolate every operation to
  datasets belonging to that member's organization. The organization boundary MUST be derived
  from the validated authenticated identity; callers MUST NOT be able to authorize themselves by
  supplying an arbitrary organization identifier.
- **FR-020**: System MUST normalize supported bot responses into the same conversation-turn
  representation. Unsupported or malformed response shapes MUST be recorded as structured bot
  failures without aborting unrelated conversations.
- **FR-021**: System MUST include structured document and bot failures in persisted datasets and
  in both local export formats so partial failures remain inspectable after the generation run.

### Key Entities *(include if feature involves data)*

- **Persona**: A configured user profile used to style generated content (e.g. "IT Manager",
  "Basic User", "Dissatisfied Customer", "New Customer"). Carries the attributes needed to shape
  both single-turn phrasing/tone and multi-turn conversational behavior, plus at least one
  associated scenario and expected outcome for multi-turn generation.
- **Golden**: A single generated input/expected-output pair produced from a knowledge base
  document, styled to a specific persona. The atomic unit of single-turn dataset content.
- **Simulated Conversation**: A full multi-turn exchange between a persona and the real bot,
  produced for a specific persona × scenario pairing, including the transcript and whether the
  scenario's expected outcome was reached.
- **Dataset**: A named, versioned collection of goldens and/or simulated conversations produced
  by one generation run, along with metadata identifying which bot, personas, and source
  documents it came from and when it was generated. Its semantic indexing status distinguishes
  indexed datasets from datasets awaiting or requiring indexing retry, and its organization
  identifier defines its access boundary.
- **Document Failure**: A structured record identifying a skipped source document, its failure
  stage (read or parse), and a safe error description. It is retained with the dataset and its
  exports without exposing credentials or sensitive configuration values.
- **Semantic Search Result**: A ranked reference to either a golden or conversation excerpt,
  carrying its content type, source record identifier, source dataset identifier, and relevance
  ordering.
- **Knowledge Base Document**: A company-owned source document (PDF, Markdown, or DOCX) used as
  the factual basis for single-turn golden generation.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: An evaluation engineer can go from a configured knowledge base and persona list to
  a usable set of single-turn goldens for all configured personas in a single generation run,
  without writing any goldens by hand.
- **SC-002**: An evaluation engineer can go from a configured persona/scenario list to a
  complete set of multi-turn conversation datasets against a live bot in a single generation
  run, without manually driving any conversation turns.
- **SC-003**: 100% of documents successfully placed in the configured knowledge base location
  are reflected in at least one generated golden per selected persona when the configured target
  is at least the number of readable documents; corrupted/unreadable documents are skipped and
  included in the structured failure report, while an insufficient target fails before producing
  a dataset.
- **SC-004**: A dataset generated today remains fully retrievable (all goldens, conversations,
  and metadata intact) in a later session with no regeneration required.
- **SC-005**: Searching previously generated datasets for content similar to a given topic
  returns a known relevant golden or conversation excerpt within the first three results of a
  controlled acceptance corpus, without the engineer needing to know which run or persona
  produced it.
- **SC-006**: A partial failure (one unreadable document, or one unreachable bot call during a
  multi-turn run) never causes total loss of an otherwise-successful generation run — the
  engineer still receives all successfully generated goldens/conversations plus a structured
  report containing every isolated document or bot failure.
- **SC-007**: For the same controlled bot responses, HTTP-based and direct-call integrations
  produce conversation records with identical normalized fields and status semantics.
- **SC-008**: 100% of generation, retrieval, semantic-search, export, and indexing-retry attempts
  made without a valid authenticated organization identity, or for another organization's dataset,
  are denied.

## Assumptions

- Persona definitions (profile, scenario, expected outcome) already exist or will be authored in
  the project's existing central, version-controlled configuration mechanism; this feature
  consumes that configuration rather than introducing a new way to define personas.
- The knowledge base documents referenced in single-turn generation are already vetted,
  non-sensitive, company-owned content approved for use in generating evaluation data — content
  screening/redaction is out of scope for this feature.
- "The real bot" in multi-turn generation refers to a bot already registered/reachable through
  this project's existing bot configuration, reachable either as an HTTP-exposed web service or
  as a directly invocable orchestration call; discovering or registering new bots is out of
  scope for this feature.
- Generation volume (goldens per persona, conversations per persona) is controlled by project-level
  configuration rather than being fixed in this specification or overridable per run; this feature
  only requires that such configured values exist.
- Retrieval and semantic search of persisted datasets serve the evaluation engineer's own
  workflow (dataset reuse, comparison, search) — building end-user-facing dashboards or UI for
  browsing datasets is out of scope for this feature.
- Exported local dataset files are for portability/backup/manual inspection purposes; they are
  not the system of record — the persisted dataset store is authoritative.

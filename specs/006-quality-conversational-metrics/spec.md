# Feature Specification: Quality/Safety + Conversational Metrics Integration

**Feature Branch**: `006-quality-conversational-metrics`

**Created**: 2026-07-14

**Status**: Draft

**Input**: User description: "Módulos em escopo para M3.3 — Métricas Qualidade/Segurança + Conversação:
`BiasMetric`, `ToxicityMetric`, `SummarizationMetric`, `JsonCorrectnessMetric`,
`PromptAlignmentMetric`, `ConversationalGEvalMetric`, `KnowledgeRetentionMetric`,
`RoleAdherenceMetric`, `ConversationCompletenessMetric`, `ConversationRelevancyMetric`."

## Clarifications

### Session 2026-07-14

- Q: Quais das 10 métricas devem ser adicionadas automaticamente ao `get_metrics()` de
  `RAGStrategy`/`AgentStrategy`/`ConversationStrategy` (rodando em toda avaliação), e quais ficam
  apenas registradas no `MetricFactory` (uso explícito/opt-in por bot)? → A: Split por natureza —
  `bias` e `toxicity` adicionadas às três strategies (RAG/Agent/Conversation) como checagem de
  segurança genérica; `conversation_completeness` e `turn_relevancy` fecham as duas lacunas já
  declaradas em `ConversationStrategy`; `knowledge_retention` e `role_adherence` também adicionadas
  a `ConversationStrategy` (inerentemente conversacionais); `summarization`, `json_correctness`,
  `prompt_alignment` e `conversational_g_eval` ficam apenas registradas no `MetricFactory`, uso
  opt-in por bot via configuração (dependem de parâmetros específicos de caso de uso).
- Q: `JsonCorrectnessMetric` (precisa de `expected_schema`), `PromptAlignmentMetric` (precisa de
  `prompt_instructions`) e `ConversationalGEvalMetric` (precisa de `criteria`/`evaluation_steps`)
  exigem parâmetros específicos por bot que não mapeiam de `NormalizedTrace` — como suprir essas
  configurações? → A: Novas chaves opcionais em `config/bots.yaml` (já designado pela constitution
  para "Bot configuration: metrics, schedule") — `json_schema` (caminho para uma classe Pydantic),
  `prompt_instructions` (lista de strings) e `conversational_geval_criteria` (string) — passadas
  como parâmetros extras ao `MetricFactory.create()` quando um bot declara essas chaves; bots sem
  essas chaves simplesmente não têm essas métricas disponíveis.
- Q: `RoleAdherenceMetric` (automática por FR-008) exige `ConversationalTestCase.chatbot_role`
  nativamente — a classe nativa levanta `MissingTestCaseParamsError` quando esse campo é `None`, e
  nem `NormalizedTrace` nem `bots.yaml` hoje carregam uma string de papel/persona. Como
  `chatbot_role` deve ser suprido? → A: Nova chave opcional `chatbot_role` (string) em
  `config/bots.yaml` para bots conversacionais. Quando presente, `role_adherence` roda normalmente.
  Quando ausente, a métrica continua sendo tentada automaticamente (mantém o caráter "automático" do
  FR-008 — nenhuma ação explícita do bot é necessária) mas produz o mesmo tratamento de falha isolada
  por métrica já estabelecido na seção Edge Cases (`score = null`, `passed = false`, detalhe
  descritivo do erro), sem bloquear as demais métricas do mesmo trace.
- Q: `JsonCorrectnessMetric.expected_schema` exige uma classe Pydantic `BaseModel` viva (não uma
  string nem um arquivo) — qual formato a chave `json_schema` de `bots.yaml` deve assumir, e como
  ela deve ser resolvida para uma classe em `MetricFactory.create()`? → A: Caminho de importação
  Python com ponto (ex.: `"myapp.schemas.OrderConfirmation"`), resolvido via
  `importlib.import_module` + `getattr` — a classe permanece código Python normal, versionado e
  type-checked do projeto; nenhum novo formato de arquivo ou lógica de construção dinâmica de
  modelo é introduzida.
- Q: Como um bot deve ativar explicitamente `summarization`? → A: Declarar
  `summarization` em `bots.<bot>.metrics` com `enabled: true`; a métrica não exige uma chave de
  configuração específica fora do mapeamento genérico de métricas.
- Q: Como tratar uma `NormalizedTrace.messages` contendo papéis como `system`, `tool` ou qualquer
  valor diferente de `user`/`assistant`? → A: Reprovar isoladamente as métricas conversacionais;
  `bias`/`toxicity` e as demais métricas continuam normalmente para o mesmo trace.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Fechar lacunas já declaradas de completude e relevância conversacional (Priority: P1)

Hoje, `ConversationStrategy.get_metrics()` já declara `conversation_completeness` e
`turn_relevancy` como parte do conjunto de métricas de todo bot conversacional, mas nenhuma métrica
está registrada sob esses nomes — qualquer avaliação de um bot conversacional falha antes de
produzir qualquer resultado. `ConversationCompletenessMetric` e `ConversationRelevancyMetric`
precisam ficar disponíveis, registradas sob os nomes já declarados, para que essa lista de métricas
volte a funcionar de ponta a ponta.

**Why this priority**: É a correção de um caminho hoje quebrado, não apenas uma adição de
capacidade — mesmo padrão de `task_completion` no M3.2. Sem isso, 100% das avaliações de bots
conversacionais falham antes de produzir qualquer score.

**Independent Test**: Pode ser testado isoladamente construindo um `EvaluationContext` a partir de
um `NormalizedTrace` de exemplo de bot conversacional (com `messages` preenchido) e a lista de
métricas `ConversationStrategy().get_metrics()`, executando o fluxo de avaliação, e verificando que
o `EvaluationResult` resultante contém entradas para `conversation_completeness` e `turn_relevancy`.

**Acceptance Scenarios**:

1. **Given** um `NormalizedTrace` de um bot conversacional com `messages` (múltiplos turnos)
   preenchido, **When** a avaliação é executada com a lista de métricas retornada por
   `ConversationStrategy.get_metrics()`, **Then** o `EvaluationResult` produzido contém entradas
   para `conversation_completeness` e `turn_relevancy`, cada uma com score e status individual.
2. **Given** os nomes canônicos `conversation_completeness` e `turn_relevancy` já registrados no
   `MetricFactory`, **When** `MetricFactory.create(nome, ...)` é chamado para qualquer um dos dois,
   **Then** uma instância válida é retornada sem branches específicos para essas métricas em
   `MetricFactory`, e sem alterar `EvaluationContext` ou `EvaluationResult`.

---

### User Story 2 - Detectar viés e conteúdo tóxico em qualquer tipo de bot (Priority: P2)

Um bot de qualquer tipo (RAG, agêntico ou conversacional) pode gerar uma resposta que carrega viés
ou conteúdo ofensivo — um risco de segurança/reputação que nenhuma das métricas já implementadas
(M3.1/M3.2) cobre. `BiasMetric` e `ToxicityMetric` precisam ficar disponíveis e passar a rodar
automaticamente em toda avaliação, independentemente do tipo de bot.

**Why this priority**: É uma checagem de segurança transversal — mais crítica que as métricas de
qualidade conversacional adicionais (User Story 3), mas vem depois da correção do caminho quebrado
(User Story 1).

**Independent Test**: Pode ser testado isoladamente construindo um `EvaluationContext` a partir de
um `NormalizedTrace` de exemplo de qualquer tipo de bot e a lista de métricas de
`RAGStrategy`/`AgentStrategy`/`ConversationStrategy`, executando o fluxo de avaliação, e verificando
que o `EvaluationResult` resultante contém entradas para `bias` e `toxicity` em todos os três casos.

**Acceptance Scenarios**:

1. **Given** um `NormalizedTrace` de um bot RAG, agêntico ou conversacional, **When** a avaliação é
   executada com a lista de métricas da strategy correspondente, **Then** o `EvaluationResult`
   produzido contém entradas para `bias` e `toxicity`, ao lado das métricas já existentes daquela
   strategy.
2. **Given** os nomes canônicos `bias` e `toxicity` já registrados no `MetricFactory`, **When**
   `MetricFactory.create(nome, ...)` é chamado para qualquer um dos dois, **Then** uma instância
   válida é retornada.

---

### User Story 3 - Aprofundar avaliação de qualidade conversacional (Priority: P3)

Um bot conversacional pode perder informações mencionadas em turnos anteriores ou sair do
papel/persona definido — falhas que `conversation_completeness` e `turn_relevancy` (User Story 1)
não cobrem explicitamente. `KnowledgeRetentionMetric` e `RoleAdherenceMetric` precisam ficar
disponíveis e passar a rodar automaticamente em toda avaliação de bot conversacional.

**Why this priority**: É uma expansão de cobertura sobre um fluxo que já funciona (avaliação
conversacional da User Story 1), não a correção de um caminho quebrado.

**Independent Test**: Pode ser testado isoladamente construindo um `EvaluationContext` a partir de
um `NormalizedTrace` de exemplo de bot conversacional multi-turno e `ConversationStrategy().get_metrics()`,
verificando que o `EvaluationResult` resultante contém entradas para `knowledge_retention` e
`role_adherence` ao lado das quatro métricas já produzidas pelas User Stories 1 e 2.

**Acceptance Scenarios**:

1. **Given** um `NormalizedTrace` de um bot conversacional multi-turno, **When** a avaliação é
   executada com a lista de métricas de `ConversationStrategy.get_metrics()`, **Then** o
   `EvaluationResult` produzido contém entradas para `knowledge_retention` e `role_adherence`, sem
   exigir que o chamador as solicite explicitamente.

---

### User Story 4 - Ativar métricas de qualidade sob demanda por bot (Priority: P4)

Alguns bots têm necessidades de avaliação específicas do seu caso de uso: um bot que gera resumos
precisa validar a qualidade do resumo (`SummarizationMetric`); um bot que deve responder em um
formato JSON específico precisa validar a estrutura (`JsonCorrectnessMetric`); um bot com
instruções de system prompt rígidas precisa verificar aderência (`PromptAlignmentMetric`); e um bot
com um critério de qualidade conversacional customizado precisa de uma avaliação sob medida
(`ConversationalGEvalMetric`). Essas quatro métricas precisam ficar disponíveis para ativação
explícita por bot, sem rodar automaticamente para bots que não as configuraram.

**Why this priority**: É a menor prioridade porque nenhum bot hoje está bloqueado por essas
métricas — são capacidades novas, opcionais, dependentes de configuração adicional por bot.

**Independent Test**: Pode ser testado isoladamente configurando um bot de exemplo com
`summarization.enabled: true` em `bots.<bot>.metrics` ou com as chaves `json_schema`,
`prompt_instructions` ou
`conversational_geval_criteria` em `bots.yaml`, executando a avaliação, e verificando que o
`EvaluationResult` inclui a métrica correspondente — e que um bot sem essas declarações não tenta
executá-las nem produz erro.

**Acceptance Scenarios**:

1. **Given** um bot que declara `bots.<bot>.metrics.summarization.enabled: true`, **When** a
   avaliação é executada, **Then** o `EvaluationResult` inclui uma entrada para `summarization`.
2. **Given** um bot configurado com `json_schema` apontando para uma classe Pydantic válida,
   **When** a avaliação é executada, **Then** o `EvaluationResult` inclui uma entrada para
   `json_correctness` com score e status.
3. **Given** um bot configurado com `prompt_instructions`, **When** a avaliação é executada,
   **Then** o `EvaluationResult` inclui uma entrada para `prompt_alignment`.
4. **Given** um bot configurado com `conversational_geval_criteria`, **When** a avaliação é
   executada, **Then** o `EvaluationResult` inclui uma entrada para `conversational_g_eval`.
5. **Given** um bot que NÃO habilita `summarization` em `bots.<bot>.metrics` nem declara nenhuma
   dessas chaves específicas, **When** a avaliação é executada, **Then** nenhuma dessas quatro
   métricas é tentada e nenhum erro de parâmetro ausente é gerado.

---

### Edge Cases

- Um `NormalizedTrace.messages` que contenha qualquer `Message.role` diferente de `user` ou
  `assistant` não é filtrado nem remapeado silenciosamente: cada métrica conversacional reprova de
  forma isolada (`score = null`, `passed = false`, detalhe descritivo do papel inválido), enquanto
  `bias`/`toxicity` e as demais métricas aplicáveis continuam para o mesmo trace.
- Um `NormalizedTrace` de bot conversacional sem `messages` preenchido (ou com um único turno) é
  tratado como reprovação isolada apenas das métricas conversacionais que dependem de múltiplos
  turnos (`conversation_completeness`, `turn_relevancy`, `knowledge_retention`, `role_adherence`,
  `conversational_g_eval`) — mesmo tratamento de falha isolada já estabelecido no M3.1/M3.2, sem
  bloquear `bias`/`toxicity` (que usam `input`/`actual_output`, já populados independentemente de
  `messages`) para o mesmo trace.
- Um bot com uma chave de configuração opt-in malformada (ex.: `json_schema` apontando para uma
  classe que não existe, ou `prompt_instructions` vazia) é tratado como reprovação isolada daquela
  métrica específica, com detalhe descritivo no `EvaluationResult` — não impede as demais métricas
  do mesmo trace.
- A adição de `bias`/`toxicity` a `RAGStrategy` e `AgentStrategy`, e de `knowledge_retention`/
  `role_adherence` a `ConversationStrategy`, não deve alterar o comportamento das métricas já
  existentes nessas listas — apenas adiciona nomes, nenhum nome existente é removido, reordenado ou
  tem seu comportamento alterado.
- Uma métrica cujo `measure()` levanta exceção ou estoura o timeout configurado segue exatamente o
  mesmo tratamento de isolamento por métrica já estabelecido no M3.1/M3.2 (`score = null`,
  `passed = false`, detalhe do erro) — esta feature não introduz um novo modelo de falha.
- Um bot conversacional que não declara a chave opcional `chatbot_role` em `bots.yaml` ainda tem
  `role_adherence` tentada automaticamente (não é excluída como as quatro métricas opt-in de
  FR-009/FR-011) — a tentativa falha com o mesmo tratamento de isolamento por métrica (`score =
  null`, `passed = false`, detalhe do erro `MissingTestCaseParamsError` da métrica nativa), sem
  impedir as demais métricas do mesmo trace.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST provide metric wrappers implementing the common `MetricBase` contract
  (M3.1) for the five `LLMTestCase`-based quality/safety metrics, self-registered in
  `MetricFactory` under the canonical names `bias`, `toxicity`, `summarization`,
  `json_correctness`, and `prompt_alignment`.
- **FR-002**: System MUST provide a new conversational metric base (parallel to `MetricBase`,
  wrapping DeepEval's `BaseConversationalMetric`-derived natives and constructing a
  `ConversationalTestCase`) since the existing `MetricBase._build_test_case` only supports
  `LLMTestCase` and has no path for multi-turn data.
- **FR-003**: System MUST map `NormalizedTrace.messages` entries whose roles are exactly `user` or
  `assistant` into DeepEval `Turn` objects to construct the `ConversationalTestCase` required by
  every conversational metric — this mapping does not exist prior to this feature. If any entry
  has another role, the system MUST produce the standard isolated failure for each conversational
  metric without filtering or remapping the entry and without blocking non-conversational metrics
  for the same trace.
- **FR-004**: System MUST provide metric wrappers implementing the new conversational metric base
  (FR-002) for the five conversational metrics, self-registered in `MetricFactory` under the
  canonical names `conversational_g_eval`, `knowledge_retention`, `role_adherence`,
  `conversation_completeness`, and `turn_relevancy`.
- **FR-005**: `ConversationRelevancyMetricWrapper` MUST wrap DeepEval's native `TurnRelevancyMetric`
  class (the native library has no class literally named `ConversationalRelevancyMetric`) and MUST
  register under the canonical name `turn_relevancy`, matching the name already referenced by
  `ConversationStrategy.get_metrics()` today.
- **FR-006**: The set of metrics automatically evaluated for every bot, regardless of type, MUST
  include `bias` and `toxicity` — `RAGStrategy.get_metrics()`, `AgentStrategy.get_metrics()`, and
  `ConversationStrategy.get_metrics()` MUST each gain these two additive names, without requiring
  any caller to request them explicitly.
- **FR-007**: The set of metrics automatically evaluated for every conversational bot MUST resolve
  `conversation_completeness` and `turn_relevancy` successfully — closing the currently-broken
  references in `ConversationStrategy.get_metrics()` without requiring any change to how a
  conversational bot evaluation is requested.
- **FR-008**: The set of metrics automatically evaluated for every conversational bot MUST also
  include `knowledge_retention` and `role_adherence` — `ConversationStrategy.get_metrics()` MUST
  gain these two additive names. `role_adherence` MUST be attempted for every conversational bot
  without requiring any explicit per-bot request; it MUST be sourced from an optional `chatbot_role`
  bot-configuration key (FR-010a) when present, and MUST produce the standard isolated per-metric
  failure (not a silent skip) when that key is absent for a given bot.
- **FR-010a**: (numbered out of sequence: added here during clarification, directly adjacent to the
  FR-008 `role_adherence` requirement it supports, rather than renumbered — see FR-010 for the
  sibling opt-in-key requirements this one was split from) System MUST support an optional per-bot
  configuration key — `chatbot_role` (a string) — in the bot configuration file, supplied as
  `ConversationalTestCase.chatbot_role` when constructing test cases for `role_adherence`
  evaluations of a bot that declares it.
- **FR-009**: `summarization`, `json_correctness`, `prompt_alignment`, and `conversational_g_eval`
  MUST be registered in `MetricFactory` but MUST NOT be added to any `EvaluationStrategy`'s
  automatic `get_metrics()` list — each is available only when a bot's configuration explicitly
  opts in: `summarization` through `bots.<bot>.metrics.summarization.enabled: true`, and the other
  three through their respective keys in FR-010.
- **FR-010**: System MUST support optional per-bot configuration keys — `json_schema` (a dotted
  Python import path string, e.g. `"myapp.schemas.OrderConfirmation"`, resolved to the referenced
  Pydantic `BaseModel` class via `importlib.import_module` + `getattr`), `prompt_instructions` (a
  list of strings), and `conversational_geval_criteria` (a string) — in the bot configuration
  file. A dedicated bot-metric configuration resolver MUST translate these values into generic
  metric-construction options, supplied when `MetricFactory.create()` instantiates
  `json_correctness`, `prompt_alignment`, or `conversational_g_eval` respectively for a bot that
  declares them.
- **FR-011**: A bot that does not declare the configuration key required by `json_correctness`,
  `prompt_alignment`, or `conversational_g_eval` (FR-010) MUST NOT have that metric attempted for
  its evaluations — no missing-required-argument error is raised; the metric is simply excluded
  from that bot's evaluation set.
- **FR-012**: A bot's evaluation MUST include, in addition to its `EvaluationStrategy`'s automatic
  metric list, `summarization` when enabled under `bots.<bot>.metrics`, plus any of
  `json_correctness`, `prompt_alignment`, or `conversational_g_eval` for which it has supplied the
  required configuration (FR-010) — regardless of the bot's underlying strategy type.
- **FR-013**: All ten new metrics MUST integrate with the evaluation pipeline established since
  M3.1 (threshold resolution, timeout handling, concurrent execution, per-metric failure isolation,
  result aggregation). The integration MAY make one backward-compatible generalization to
  `MetricFactory.create()` so it accepts generic keyword-only metric options and MAY extend
  `EvaluationOrchestrator` to obtain and forward the resolved options; `MetricFactory.register()`,
  `EvaluationContext`, and `EvaluationResult` MUST remain unchanged.
- **FR-014**: System MUST expose score, threshold, pass/fail status, and error detail for all ten
  new metrics through the same result contract already used by every other registered metric — no
  new or different result schema, whether the metric is `LLMTestCase`-based or
  `ConversationalTestCase`-based.
- **FR-015**: System MUST provide a `BotMetricConfigResolver` with the sole responsibility of
  reading per-bot metric declarations through `ConfigManager`, merging opt-in metrics with the
  strategy's automatic list, and returning constructor options keyed by canonical metric name.
  The resolver MUST contain no metric instantiation or evaluation logic.
- **FR-016**: `MetricFactory.create()` MUST forward generic keyword-only metric options to the
  selected registered wrapper without branching on canonical metric names. Existing calls that
  supply only `threshold` and `deepeval_model` MUST remain valid, and adding a future configurable
  metric MUST NOT require another change to the factory or orchestrator.

### Key Entities *(include if feature involves data)*

- **BiasMetricWrapper**, **ToxicityMetricWrapper**: New `MetricBase` subclasses wrapping DeepEval's
  native bias/toxicity metrics; added to all three existing strategies as a cross-cutting safety
  check.
- **SummarizationMetricWrapper**: New `MetricBase` subclass wrapping DeepEval's native
  summarization metric; registered but not auto-wired into any strategy.
- **JsonCorrectnessMetricWrapper**: New `MetricBase` subclass wrapping DeepEval's native
  `JsonCorrectnessMetric`; requires a per-bot `json_schema` configuration value (a dotted Python
  import path resolved via `importlib`) to be usable.
- **PromptAlignmentMetricWrapper**: New `MetricBase` subclass wrapping DeepEval's native
  `PromptAlignmentMetric`; requires a per-bot `prompt_instructions` configuration value.
- **ConversationalMetricBase**: New sibling to `MetricBase` (M3.1), responsible for constructing a
  `ConversationalTestCase` from `NormalizedTrace.messages` (mapped to DeepEval `Turn` objects) and
  driving `a_measure()` against DeepEval's `BaseConversationalMetric`-derived natives.
- **ConversationalGEvalMetricWrapper**: New `ConversationalMetricBase` subclass wrapping DeepEval's
  native `ConversationalGEval`; requires a per-bot `conversational_geval_criteria` configuration
  value.
- **BotMetricConfigResolver**: New configuration-domain class that reads bot metric settings only
  through `ConfigManager`, merges explicit opt-ins with the strategy metric list, and produces
  generic constructor options per canonical metric name. It does not instantiate or execute
  metrics.
- **ConversationCompletenessMetricWrapper**: New `ConversationalMetricBase` subclass wrapping
  DeepEval's native `ConversationCompletenessMetric`; its canonical name is already declared in
  `ConversationStrategy.get_metrics()` today but unresolvable, so this wrapper implements the
  missing piece (FR-007) rather than adding a new entry to the list.
- **KnowledgeRetentionMetricWrapper**, **RoleAdherenceMetricWrapper**: New `ConversationalMetricBase`
  subclasses wrapping DeepEval's native equivalents; newly added to `ConversationStrategy.get_metrics()`
  (FR-008). `RoleAdherenceMetricWrapper` additionally reads the optional per-bot `chatbot_role`
  configuration key (FR-010a) to populate `ConversationalTestCase.chatbot_role`, required by the
  native metric.
- **ConversationRelevancyMetricWrapper**: New `ConversationalMetricBase` subclass wrapping
  DeepEval's native `TurnRelevancyMetric`; registered under `turn_relevancy`, closing the gap
  already declared in `ConversationStrategy.get_metrics()`.
- **RAGStrategy**, **AgentStrategy** *(modified)*: `get_metrics()` gains the additive `"bias"` and
  `"toxicity"` metric names — no other change.
- **ConversationStrategy** *(modified)*: `get_metrics()` grows from two declared-but-unregistered
  names to six fully working names (`conversation_completeness`, `turn_relevancy`, `bias`,
  `toxicity`, `knowledge_retention`, `role_adherence`).
- **MetricFactory** *(modified once)*: `create()` gains backward-compatible generic keyword-only
  metric options and forwards them to registered wrappers without metric-specific branches;
  `register()` and registry behavior remain unchanged.
- **EvaluationOrchestrator** *(modified)*: obtains the bot's merged metric list and constructor
  options from `BotMetricConfigResolver`, then forwards those options during metric creation; its
  concurrency, timeout, isolation, and aggregation behavior remain unchanged.
- **Bot configuration schema** *(modified)*: uses
  `bots.<bot>.metrics.summarization.enabled: true` to opt in to `summarization` and gains four new
  optional per-bot keys — `json_schema`,
  `prompt_instructions`, `conversational_geval_criteria` (each unlocking one opt-in metric when
  present) and `chatbot_role` (a string consumed by the always-attempted `role_adherence` metric;
  its absence causes an isolated per-metric failure rather than excluding the metric, unlike the
  other three keys).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of conversational-bot trace evaluations produce results for
  `conversation_completeness` and `turn_relevancy`, versus 0% today (both currently fail with an
  unknown-metric error).
- **SC-002**: 100% of bot trace evaluations, regardless of type (RAG, agentic, conversational),
  produce `bias` and `toxicity` results alongside their existing metrics, with zero change required
  to how any bot evaluation is requested.
- **SC-003**: 100% of conversational-bot trace evaluations also produce `knowledge_retention` and
  `role_adherence` results automatically, growing `ConversationStrategy`'s working automatic metric
  count from zero (both existing names unregistered) to six.
- **SC-004**: A bot that sets `bots.<bot>.metrics.summarization.enabled: true`, or supplies the
  required configuration for `json_correctness`, `prompt_alignment`, or `conversational_g_eval`,
  successfully receives a result for that metric; a bot that does not opt in is entirely
  unaffected — no error, no attempted execution.
- **SC-005**: A failure or timeout in any one of the ten new metrics never prevents the other
  metrics evaluated for the same trace from completing and reporting their own result.
- **SC-006**: Delivering all ten metrics requires new metric wrapper classes, one conversational
  test-case construction path, strategy list updates, new optional bot-configuration keys, one
  `BotMetricConfigResolver`, and only backward-compatible integration changes to
  `MetricFactory.create()` and `EvaluationOrchestrator`; `MetricFactory.register()`,
  `EvaluationContext`, and `EvaluationResult` remain unchanged.
- **SC-007**: After this feature, a new configurable metric can be added with a registered wrapper
  and bot configuration only, without further changes to `MetricFactory`,
  `EvaluationOrchestrator`, `EvaluationContext`, or `EvaluationResult`.

## Assumptions

- `ConversationRelevancyMetric`, as named in the feature request, maps to DeepEval's native
  `TurnRelevancyMetric` class — the only native class matching that intent — and is registered
  under the canonical name `turn_relevancy` to match the name `ConversationStrategy.get_metrics()`
  already references today.
- `NormalizedTrace.messages` (role/content pairs) already carries the data needed to construct
  conversational test cases; this milestone only adds the mapping into DeepEval `Turn` objects, it
  does not add new fields to `NormalizedTrace` itself.
- `bias` and `toxicity` operate on `NormalizedTrace.input`/`output` (already populated for every
  bot type since M3.1) and therefore work uniformly across `RAGStrategy`, `AgentStrategy`, and
  `ConversationStrategy` without needing conversational test-case construction.
- Threshold and timeout configuration for all ten new metrics follow the exact same
  `ConfigManager`-based resolution and native-default fallback already implemented generically by
  `EvaluationOrchestrator` since M3.1 — no new configuration mechanism is introduced for those two
  aspects.
- The three new opt-in bot-configuration keys (`json_schema`, `prompt_instructions`,
  `conversational_geval_criteria`) are read through the existing `ConfigManager` Singleton
  (Principle V / VI) — no module other than `ConfigManager` reads `bots.yaml` directly.
- The one-time generalization of `MetricFactory.create()` and the addition of
  `BotMetricConfigResolver` establish the extension point required by parameterized metrics;
  subsequent configurable metrics use that extension point without changing existing factory or
  orchestration code.

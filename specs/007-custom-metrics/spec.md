# Feature Specification: Custom Metrics Integration (GEval, DAG, Ragas)

**Feature Branch**: `007-custom-metrics`

**Created**: 2026-07-15

**Status**: Draft

**Input**: User description: "Módulos em escopo para M3.4 — Métricas Custom:
`GEvalMetric` — wrapper do GEval do DeepEval; critérios de avaliação carregados do
`config/bots/*.yaml`. `DAGMetricWrapper` — wrapper do DAGMetric do DeepEval; grafo de decisão
definido em YAML ou Python. `RagasMetricWrapper` — integra métricas do Ragas (Answer Correctness,
Context Recall) via interface `MetricBase`."

## Clarifications

### Session 2026-07-15

- Q: Como o grafo de decisão (nós, condições, veredictos) do `DAGMetricWrapper` deve ser suprido
  por bot? → A: Caminho de importação Python — uma chave em `config/bots.yaml` aponta para uma
  função/classe que constrói o `DeepAcyclicGraph` nativo, resolvida via `importlib` — mesmo padrão
  já usado para `json_schema` no M3.3. Código versionado e type-checked; nenhum parser de grafo
  genérico é introduzido.
- Q: As duas métricas Ragas (`ragas_answer_correctness`, `ragas_context_recall`) devem rodar
  automaticamente em todo bot RAG (como `bias`/`toxicity` desde M3.3) ou apenas quando um bot
  habilita explicitamente cada uma? → A: Opt-in por bot — mesmo padrão já usado para
  `summarization`/`json_correctness`/`prompt_alignment` (M3.3). Evita duplicar custo/latência de
  LLM sobre bots já cobertos por `faithfulness`/`contextual_precision`/`contextual_recall` nativos
  do DeepEval.
- Q: Ragas espera um LLM/embeddings compatíveis com sua própria interface (tipicamente wrappers
  LangChain), diferente de `DeepEvalBaseLLM` já usado por `MetricBase`/providers deste projeto
  (Princípio III designa LangChain como camada de orquestração de bot, não de avaliação) — qual
  fonte de configuração o `RagasMetricWrapper` deve usar para o LLM/embeddings que julgam as
  métricas Ragas? → A: Reaproveitar o provider já configurado do bot — um adaptador traduz o
  `DeepEvalBaseLLM` (GPTModel/AnthropicModel/OpenRouterModel) já configurado para o bot para a
  interface esperada pelo Ragas. Nenhuma configuração de LLM nova é introduzida.
- Q: Qual restrição de versão deve ser fixada para a nova dependência `ragas` em `pyproject.toml`?
  → A: `>=0.2.0` — API estável atual (baseada em `SingleTurnSample`), consistente com o padrão `>=`
  já usado para Langfuse (`>=4.13.0`) neste projeto.
- Q: Qual deve ser o nome da chave de configuração por bot em `config/bots.yaml` para o critério de
  texto livre do GEval (FR-002)? → A: `geval_criteria` — espelha `conversational_geval_criteria`
  (M3.3) sem o prefixo `conversational_`, lida diretamente como a contraparte de turno único.
- Q: Qual deve ser o nome da chave de configuração por bot em `config/bots.yaml` para o caminho de
  importação do construtor do DAG (FR-005)? → A: `dag_builder` — nome curto que identifica o papel
  da função/classe referenciada (ela constrói o `DeepAcyclicGraph`).
- Q: A ativação do `dag` deve ser possível somente por alteração em YAML, apesar de `dag_builder`
  referenciar código Python? → A: O `dag` requer uma função/classe Python versionada e type-checked
  para construir o grafo; a ativação puramente por YAML aplica-se a `g_eval` e às duas métricas
  Ragas, sem introduzir um parser declarativo de DAG.
- Q: Quais campos devem fornecer os dados de referência para as métricas Ragas? → A: Reutilizar
  `NormalizedTrace.expected_output` como resposta esperada e `NormalizedTrace.context` como
  contextos recuperados; nenhum campo específico para Ragas será adicionado.
- Q: Ragas Answer Correctness combina um score de correção factual (julgado por LLM) com um score
  de similaridade semântica, que requer um modelo de embeddings — separado do LLM juiz coberto pelo
  FR-009. De onde `RagasMetricWrapper` deve obter esse modelo de embeddings? → A: Reaproveitar a
  configuração global de embeddings já existente (`embedding.model`/`embedding.dimensions` em
  `config/settings.yaml`, mesmo padrão `OpenAIEmbeddings` já usado por `QdrantVectorStoreProvider`)
  — nenhum novo provider ou caminho de configuração de embeddings é introduzido.
- Q: `dag_builder` (FR-005) diz apontar para "uma função ou classe que constrói o
  `DeepAcyclicGraph`" e afirma seguir o mesmo padrão de `json_schema` (M3.3) — mas o resolver real
  de `json_schema` (`_resolve_json_correctness_options`) nunca invoca nada: faz
  `getattr(module, class_name)` e usa o valor resolvido diretamente. Para `dag_builder`, o atributo
  resolvido deve ser invocado para produzir o grafo, ou usado diretamente sem invocação (igual a
  `json_schema`)? → A: Invocado como callable sem argumentos — `dag_builder` resolve para uma
  função ou classe que `BotMetricConfigResolver` chama sem argumentos para obter o
  `DeepAcyclicGraph`; casa com o texto literal do FR-005 ("que retorna o `DeepAcyclicGraph`") e
  permite construção tardia (lazy) do grafo pelo autor do bot, em vez de no momento do import.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Avaliar critérios de qualidade customizados por bot com GEval (Priority: P1)

Um bot pode ter um critério de qualidade específico do seu caso de uso — por exemplo, "a resposta
deve manter tom formal e nunca prometer prazos" — que nenhuma das métricas nativas já integradas
(M3.1-M3.3) cobre, porque são fixas nos critérios que o DeepEval já embute. `GEvalMetricWrapper`
precisa ficar disponível para que qualquer bot declare seu próprio critério de avaliação em texto
livre e receba um score/veredito julgado por LLM sobre esse critério.

**Why this priority**: É o padrão de customização mais simples e com maior precedente já validado
no projeto (`conversational_geval_criteria` do M3.3, mesmo mecanismo aplicado ao caso de turno
único) — menor risco de implementação e maior valor imediato para bots com necessidades de
avaliação não cobertas pelas métricas fixas.

**Independent Test**: Pode ser testado isoladamente configurando um bot de exemplo com o critério
de avaliação customizado em `config/bots.yaml`, construindo um `EvaluationContext` a partir de um
`NormalizedTrace` desse bot, executando a avaliação com `g_eval` na lista de métricas, e verificando
que o `EvaluationResult` resultante contém uma entrada para `g_eval` com score e status.

**Acceptance Scenarios**:

1. **Given** um bot que declara um critério de avaliação customizado em `config/bots.yaml`,
   **When** a avaliação é executada com `g_eval` na lista de métricas, **Then** o
   `EvaluationResult` produzido contém uma entrada para `g_eval` com score, threshold e status
   individual, julgados segundo o critério declarado.
2. **Given** o nome canônico `g_eval` já registrado no `MetricFactory`, **When**
   `MetricFactory.create("g_eval", ...)` é chamado com o critério do bot como opção, **Then** uma
   instância válida é retornada sem branches específicos de `g_eval` em `MetricFactory`.
3. **Given** um bot que NÃO declara nenhum critério de avaliação customizado, **When** a avaliação
   é executada, **Then** `g_eval` não é tentada para esse bot e nenhum erro de parâmetro ausente é
   gerado.

---

### User Story 2 - Avaliar fluxos determinísticos com um grafo de decisão (DAG) (Priority: P2)

Alguns bots seguem um fluxo de decisão estruturado (ex.: "se a resposta menciona reembolso, então
verificar se cita o prazo de 7 dias; senão, verificar se a resposta é uma recusa educada") que uma
avaliação de critério único em texto livre (User Story 1) não expressa bem — é mais natural como
uma sequência de julgamentos condicionais. `DAGMetricWrapper` precisa ficar disponível para que um
bot declare esse fluxo como um grafo de decisão e receba um veredito determinístico baseado nele.

**Why this priority**: Depende do mesmo padrão de wrapper e registro estabelecido pela User Story
1, mas introduz uma estrutura de configuração mais complexa (grafo, não um critério simples) — por
isso vem depois em prioridade, mesmo sendo tecnicamente independente.

**Independent Test**: Pode ser testado isoladamente configurando um bot de exemplo com uma
definição de grafo de decisão válida, construindo um `EvaluationContext` a partir de um
`NormalizedTrace` desse bot, executando a avaliação com `dag` na lista de métricas, e verificando
que o `EvaluationResult` resultante contém uma entrada para `dag` com score e status.

**Acceptance Scenarios**:

1. **Given** um bot que declara uma definição de grafo de decisão válida, **When** a avaliação é
   executada com `dag` na lista de métricas, **Then** o `EvaluationResult` produzido contém uma
   entrada para `dag` com score, threshold e status individual, seguindo o percurso determinístico
   do grafo declarado.
2. **Given** o nome canônico `dag` já registrado no `MetricFactory`, **When**
   `MetricFactory.create("dag", ...)` é chamado com a definição de grafo do bot como opção,
   **Then** uma instância válida é retornada sem branches específicos de `dag` em `MetricFactory`.
3. **Given** um bot que NÃO declara nenhuma definição de grafo de decisão, **When** a avaliação é
   executada, **Then** `dag` não é tentada para esse bot e nenhum erro de parâmetro ausente é
   gerado.

---

### User Story 3 - Comparar respostas RAG contra métricas de referência do Ragas (Priority: P3)

Times que já usam o framework Ragas como referência de mercado para avaliação RAG (Answer
Correctness, Context Recall) querem comparar os scores desse framework lado a lado com as métricas
nativas do DeepEval já integradas (M3.1), sem adotar Ragas como motor de avaliação principal do
projeto. `RagasMetricWrapper` precisa ficar disponível para que um bot RAG opte por essas duas
métricas adicionais através da mesma interface `MetricBase` já usada por todas as demais.

**Why this priority**: É a menor prioridade porque introduz uma dependência externa nova (o pacote
Ragas, hoje ausente do projeto) e um framework de avaliação secundário — nenhum bot está bloqueado
por essa capacidade hoje; é uma comparação/validação cruzada opcional, não uma lacuna de cobertura.

**Independent Test**: Pode ser testado isoladamente habilitando as métricas Ragas para um bot RAG
de exemplo, construindo um `EvaluationContext` a partir de um `NormalizedTrace` desse bot,
executando a avaliação, e verificando que o `EvaluationResult` resultante contém entradas para
`ragas_answer_correctness` e `ragas_context_recall`.

**Acceptance Scenarios**:

1. **Given** um bot RAG com as métricas Ragas habilitadas, **When** a avaliação é executada,
   **Then** o `EvaluationResult` produzido contém entradas para `ragas_answer_correctness` e
   `ragas_context_recall`, cada uma com score, threshold e status individual.
2. **Given** os nomes canônicos `ragas_answer_correctness` e `ragas_context_recall` já registrados
   no `MetricFactory`, **When** `MetricFactory.create(nome, ...)` é chamado para qualquer um dos
   dois, **Then** uma instância válida é retornada sem branches específicos dessas métricas em
   `MetricFactory`.
3. **Given** um bot RAG que NÃO habilita as métricas Ragas, **When** a avaliação é executada,
   **Then** nenhuma das duas métricas é tentada e nenhum erro de dependência ou parâmetro ausente é
   gerado.

---

### Edge Cases

- Um bot que declara um critério de `g_eval` malformado é tratado como reprovação isolada apenas de
  `g_eval` (`score = null`, `passed = false`, detalhe descritivo do erro), sem impedir as demais
  métricas do mesmo trace — mesmo tratamento de falha isolada já estabelecido desde M3.1. Um
  critério vazio (`geval_criteria: ""`) não dispara essa falha isolada: por ser falsy, o resolver o
  trata como ausente (caminho de FR-003, "não tentado, sem erro").
- Um bot que declara uma definição de grafo de decisão inválida (ciclo, nó órfão, referência
  quebrada) é tratado como reprovação isolada apenas de `dag`, com detalhe descritivo do erro de
  construção do grafo, sem impedir as demais métricas do mesmo trace.
- Uma tentativa de avaliação com uma métrica Ragas quando o pacote `ragas` não está instalado ou
  suas credenciais/configuração de LLM estão ausentes é tratada como reprovação isolada apenas
  daquela métrica Ragas específica, com detalhe descritivo do erro, sem impedir as demais métricas
  (nativas DeepEval ou não) do mesmo trace.
- Um bot que habilita `g_eval`, `dag` e as duas métricas Ragas simultaneamente tem todas avaliadas
  de forma independente e concorrente, seguindo o mesmo pipeline de execução, timeout e isolamento
  por métrica já estabelecido — nenhuma dessas quatro métricas bloqueia ou depende do resultado das
  outras para o mesmo trace.
- Uma métrica Ragas cujo `measure()` levanta exceção ou estoura o timeout configurado segue
  exatamente o mesmo tratamento de isolamento por métrica já estabelecido desde M3.1 (`score =
  null`, `passed = false`, detalhe do erro) — esta feature não introduz um novo modelo de falha.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST provide a `GEvalMetricWrapper` implementing the existing `MetricBase`
  contract (M3.1), wrapping DeepEval's native `GEval` metric, self-registered in `MetricFactory`
  under the canonical name `g_eval`.
- **FR-002**: System MUST support an optional per-bot configuration key, `geval_criteria`, in
  `config/bots.yaml` supplying the free-text evaluation criteria consumed by `GEvalMetricWrapper`'s
  underlying `GEval(criteria=...)` construction — parallel to the existing
  `conversational_geval_criteria` key introduced in M3.3, but for the single-turn (`LLMTestCase`-
  based) case.
- **FR-003**: `g_eval` MUST be registered in `MetricFactory` but MUST NOT be added to any
  `EvaluationStrategy`'s automatic `get_metrics()` list — it is available only when a bot's
  configuration declares the criteria key from FR-002. A bot that does not declare it MUST NOT
  have `g_eval` attempted, and no missing-required-argument error MUST be raised.
- **FR-004**: System MUST provide a `DAGMetricWrapper` implementing the `MetricBase` contract,
  wrapping DeepEval's native `DAGMetric` (and its supporting `DeepAcyclicGraph`/node classes),
  self-registered in `MetricFactory` under the canonical name `dag`.
- **FR-005**: System MUST support an optional per-bot configuration key, `dag_builder`, in
  `config/bots.yaml` — a dotted Python import path string (e.g.
  `"myapp.dags.refund_flow.build_dag"`), resolved via `importlib.import_module` + `getattr`,
  reusing the same import-resolution mechanism already established for `json_schema` in M3.3 —
  pointing to a zero-argument callable (function or class) that `BotMetricConfigResolver` MUST
  invoke, with no arguments, to obtain the `DeepAcyclicGraph` consumed by `DAGMetricWrapper`'s
  underlying `DAGMetric(dag=...)` construction. Unlike `json_schema` (whose resolved attribute is
  used as-is, never called), `dag_builder`'s resolved attribute MUST always be invoked.
- **FR-006**: `dag` MUST be registered in `MetricFactory` but MUST NOT be added to any
  `EvaluationStrategy`'s automatic `get_metrics()` list — it is available only when a bot's
  configuration declares the graph definition from FR-005. A bot that does not declare it MUST NOT
  have `dag` attempted, and no missing-required-argument error MUST be raised.
- **FR-007**: System MUST provide a `RagasMetricWrapper` implementing the `MetricBase` contract,
  parameterized by which underlying Ragas metric to compute. `RagasMetricWrapper` MUST back two
  directly-registered thin subclasses, each self-registered in `MetricFactory` under its own
  canonical name: `ragas_answer_correctness` (wrapping Ragas' Answer Correctness metric) and
  `ragas_context_recall` (wrapping Ragas' Context Recall metric).
- **FR-008**: `ragas_answer_correctness` and `ragas_context_recall` MUST be registered in
  `MetricFactory` but MUST NOT be added to `RAGStrategy`'s automatic `get_metrics()` list — each is
  available only when a bot's configuration explicitly opts in (per-metric enable key in
  `config/bots.yaml`, following the same `bots.<bot>.metrics.<name>.enabled: true` pattern already
  used for `summarization` in M3.3). A bot that does not opt in MUST NOT have either metric
  attempted, and no missing-dependency or missing-parameter error MUST be raised.
- **FR-009**: `RagasMetricWrapper` MUST obtain the LLM it uses to judge Ragas metrics by adapting
  the same `DeepEvalBaseLLM` provider already configured for the bot
  (`GPTModel`/`AnthropicModel`/`OpenRouterModel` via `LLMProviderFactory`) to the interface Ragas
  expects, via a dedicated adapter class. This MUST NOT alter the constructor contract or behavior
  of `LLMProviderFactory` or any existing `DeepEvalBaseLLM` provider used by other metric wrappers,
  and MUST NOT introduce a separate, Ragas-specific LLM configuration path.
- **FR-010**: System MUST add `ragas` as a new project dependency, pinned to `>=0.2.0` (the
  `SingleTurnSample`-based stable API); its absence or misconfiguration MUST NOT prevent any
  non-Ragas metric from evaluating for the same bot or trace.
- **FR-011**: All four new metrics (`g_eval`, `dag`, `ragas_answer_correctness`,
  `ragas_context_recall`) MUST integrate with the evaluation pipeline established since M3.1
  (threshold resolution, timeout handling, concurrent execution, per-metric failure isolation,
  result aggregation) without requiring any change to `MetricFactory.register()`,
  `EvaluationContext`, or `EvaluationResult`.
- **FR-012**: The mechanism that resolves per-bot opt-in metric configuration into constructor
  options (`BotMetricConfigResolver`, introduced in M3.3) MUST be extended to cover the new
  configuration keys from FR-002, FR-005, and FR-008 (if opt-in), reading exclusively through
  `ConfigManager` as it already does for every other opt-in metric, with no metric instantiation or
  evaluation logic added to it.
- **FR-013**: System MUST expose score, threshold, pass/fail status, and error detail for all four
  new metrics through the same `MetricResult` contract already used by every other registered
  metric — no new or different result schema.
- **FR-014**: `RagasMetricWrapper` MUST obtain the embeddings model required by Ragas Answer
  Correctness' semantic-similarity component by reusing the project's existing global embedding
  configuration (`embedding.model`/`embedding.dimensions` in `config/settings.yaml`, read via
  `ConfigManager`), instantiating it the same way `QdrantVectorStoreProvider` already does
  (`OpenAIEmbeddings`). This MUST NOT introduce a new embeddings provider, a Ragas-specific
  embeddings configuration path, or any change to `QdrantVectorStoreProvider`.

### Key Entities *(include if feature involves data)*

- **GEvalMetricWrapper**: New `MetricBase` subclass wrapping DeepEval's native `GEval`; requires a
  per-bot free-text criteria configuration value (FR-002, key `geval_criteria`) to be usable;
  registered but not auto-wired into any strategy.
- **DAGMetricWrapper**: New `MetricBase` subclass wrapping DeepEval's native `DAGMetric`; requires a
  per-bot dotted Python import path (FR-005, key `dag_builder`), resolved via `importlib` and then
  invoked as a zero-argument callable to build the `DeepAcyclicGraph`; registered but not
  auto-wired into any strategy.
- **RagasMetricWrapper**: New `MetricBase` subclass adapting Ragas' Answer Correctness and Context
  Recall metrics to the project's `MetricBase` contract; parameterized by which Ragas metric to
  compute; backs two directly-registered thin subclasses, each self-registered under its own
  canonical name (FR-007); opt-in per bot (FR-008); obtains its
  judge LLM via a new adapter over the bot's existing `DeepEvalBaseLLM` provider (FR-009); obtains
  its embeddings model (Answer Correctness only) by reusing the project's global embedding
  configuration, the same way `QdrantVectorStoreProvider` does (FR-014); uses
  `NormalizedTrace.expected_output` as the reference answer and `NormalizedTrace.context` as the
  retrieved-context input.
- **RagasLLMAdapter** (or equivalent): New adapter class translating a `DeepEvalBaseLLM` provider
  instance into the LLM interface Ragas expects, used exclusively by `RagasMetricWrapper`; does not
  modify `LLMProviderFactory` or any existing provider class.
- **BotMetricConfigResolver** *(modified)*: gains resolution logic for the new opt-in configuration
  keys backing `g_eval`, `dag`, `ragas_answer_correctness`, and `ragas_context_recall`, following
  the same per-metric-name dispatch pattern already established for `json_correctness`,
  `prompt_alignment`, and `conversational_g_eval` in M3.3.
- **Bot configuration schema** (`config/bots.yaml`) *(modified)*: gains new optional per-bot keys —
  `geval_criteria` (string), `dag_builder` (dotted import-path string), and
  `bots.<bot>.metrics.ragas_answer_correctness.enabled` /
  `bots.<bot>.metrics.ragas_context_recall.enabled` — following the same pattern as the M3.3 opt-in
  keys (`json_schema`, `prompt_instructions`, `conversational_geval_criteria`,
  `summarization.enabled`).
- **`pyproject.toml`** *(modified)*: gains `ragas>=0.2.0` as a new direct dependency.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A bot that declares a custom GEval criterion successfully receives a `g_eval` result;
  a bot that does not declare one is entirely unaffected — no error, no attempted execution.
- **SC-002**: A bot that declares a valid decision-graph definition successfully receives a `dag`
  result; a bot that does not declare one is entirely unaffected — no error, no attempted
  execution.
- **SC-003**: A bot with Ragas metrics enabled successfully receives `ragas_answer_correctness` and
  `ragas_context_recall` results; a bot without them enabled is entirely unaffected — no error, no
  attempted execution, no required dependency check performed on its behalf.
- **SC-004**: A failure, malformed configuration, or timeout in any one of the four new metrics
  never prevents the other metrics evaluated for the same trace — including the three already
  covered by this same guarantee since M3.1-M3.3 — from completing and reporting their own result.
- **SC-005**: Delivering all four new metrics requires only new metric wrapper classes, one new
  project dependency (`ragas`), new optional bot-configuration keys, and a backward-compatible
  extension to `BotMetricConfigResolver`; `MetricFactory.register()`, `MetricFactory.create()`,
  `EvaluationContext`, and `EvaluationResult` remain unchanged.
- **SC-006**: After this feature, a bot operator can activate `g_eval`, `ragas_answer_correctness`,
  and `ragas_context_recall` purely through `config/bots.yaml` changes. Activating `dag` additionally
  requires implementing the versioned Python function/class referenced by `dag_builder`, without
  modifying the evaluation pipeline code.

## Assumptions

- `config/bots.yaml` remains the single project-wide bot configuration file (as established since
  M1) — the feature description's reference to `config/bots/*.yaml` is read as referring to this
  existing file's per-bot blocks (`bots.<bot_id>.*`), not a new per-bot file layout; no new
  configuration file or directory structure is introduced.
- `GEvalMetricWrapper` supports GEval's free-text `criteria` parameter only for this milestone (not
  the alternative `evaluation_steps` list or `rubric` parameters DeepEval's native `GEval` also
  accepts) — matching the minimal single-field pattern already used for
  `conversational_geval_criteria` in M3.3. Broader GEval configuration (explicit steps, rubrics) is
  out of scope and can be added later without changing the canonical name or registration.
- The canonical metric name `g_eval` is used for the new single-turn wrapper to avoid collision
  with the existing `conversational_g_eval` name (M3.3), which wraps DeepEval's distinct
  `ConversationalGEval` class.
- Threshold and timeout configuration for all four new metrics follow the exact same
  `ConfigManager`-based resolution and native-default fallback already implemented generically by
  `EvaluationOrchestrator` since M3.1 — no new configuration mechanism is introduced for those two
  aspects.
- Adding `ragas` as a new dependency does not replace or compete with DeepEval as this project's
  primary evaluation framework (Constitution Principle II) — `RagasMetricWrapper` exists solely to
  expose Ragas' scores through the project's own `MetricBase` interface for side-by-side comparison
  with DeepEval-native RAG metrics, not to reimplement or supersede them.
- `DAGMetricWrapper`'s decision-graph import path is resolved once per metric construction (not
  cached across bots) — matching the existing `json_schema` resolution behavior from M3.3; no new
  caching mechanism is introduced.
- The Ragas judge-LLM adapter (FR-009) only needs to support the subset of the Ragas LLM interface
  actually exercised by Answer Correctness and Context Recall; it is not a general-purpose
  DeepEvalBaseLLM-to-Ragas compatibility layer for the full Ragas metric catalog.

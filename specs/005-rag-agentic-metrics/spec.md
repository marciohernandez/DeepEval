# Feature Specification: HallucinationMetric + TaskCompletionMetric Integration

**Feature Branch**: `005-rag-agentic-metrics`

**Created**: 2026-07-14

**Status**: Draft

**Input**: User description: "Módulos em escopo para M3.2 — Métricas RAG + Agênticas:
`AnswerRelevancyMetric`, `FaithfulnessMetric`, `ContextualPrecisionMetric`,
`ContextualRecallMetric`, `ContextualRelevancyMetric`, `HallucinationMetric`,
`ToolCorrectnessMetric`, `TaskCompletionMetric`. Todos implementam `MetricBase` do M3.1.
Necessario criar a branch para seguir daqui pra frente."

## Clarifications

### Session 2026-07-14

- Q: O M3.1 (já mergeado) implementou wrappers para 6 dos 8 nomes listados
  (`answer_relevancy`, `faithfulness`, `contextual_precision`, `contextual_recall`,
  `contextual_relevancy`, `tool_correctness`). Como ajustar o escopo do M3.2? → A: Reduzir o
  escopo desta feature aos dois nomes que ainda não têm wrapper: `HallucinationMetric` e
  `TaskCompletionMetric`. As seis métricas já implementadas ficam fora desta spec.
- Q: `AgentStrategy.get_metrics()` (M2.1) já referencia `"task_completion"`, mas nenhum wrapper
  está registrado sob esse nome — toda avaliação de bot agêntico falha hoje com um erro de
  métrica desconhecida. Isso confirma `TaskCompletionMetric` como item bloqueante desta spec,
  não apenas uma adição de capacidade. Nenhuma pergunta adicional necessária aqui — apenas
  registrado como contexto que eleva a prioridade de `TaskCompletionMetric`.
- Q: `HallucinationMetric` não está referenciada por nenhuma `EvaluationStrategy` existente
  (`RAGStrategy.get_metrics()` retorna hoje as cinco métricas RAG já implementadas no M3.1, sem
  `hallucination`). O M3.2 deve adicioná-la a essa lista, passando a rodar automaticamente em
  todo bot RAG, ou apenas registrar o wrapper no `MetricFactory` sem alterar `RAGStrategy`? → A:
  Adicionar `"hallucination"` a `RAGStrategy.get_metrics()`, para que passe a rodar
  automaticamente em toda avaliação de bot RAG junto com as cinco métricas já existentes.
- Q: A `HallucinationMetric` nativa do DeepEval declara `context` (campo `LLMTestCase.context`)
  como parâmetro obrigatório — distinto de `retrieval_context`, que é o único campo que
  `MetricBase._build_test_case` (compartilhado por todos os wrappers desde o M3.1) já popula a
  partir de `trace.context`. Sem ajuste, `context` chega sempre `None` e `HallucinationMetric`
  falharia em 100% das avaliações de bot RAG, não apenas como caso de borda isolado. Como
  `HallucinationMetricWrapper` deve suprir esse campo obrigatório? → A: `HallucinationMetricWrapper`
  sobrescreve a construção do `LLMTestCase` apenas na própria classe, populando `context` a partir
  do mesmo `trace.context` já usado para `retrieval_context` — sem alterar `MetricBase` nem
  nenhum dos outros seis wrappers já registrados.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Avaliar completude de tarefa em bots agênticos sem erro de métrica desconhecida (Priority: P1)

Hoje, `AgentStrategy.get_metrics()` já declara `"task_completion"` como parte do conjunto de
métricas de todo bot agêntico, mas nenhuma métrica está registrada sob esse nome — qualquer
avaliação de um bot agêntico falha antes de produzir qualquer resultado. Um `TaskCompletionMetric`
precisa ficar disponível, registrado sob o nome `task_completion`, para que essa lista de métricas
já declarada volte a funcionar de ponta a ponta.

**Why this priority**: É a correção de um caminho hoje quebrado, não apenas uma adição de
capacidade — sem isso, 100% das avaliações de bots agênticos falham antes de produzir qualquer
score, incluindo a métrica `tool_correctness` que já está implementada. Nenhum outro trabalho de
avaliação agêntica pode prosseguir enquanto esse nome permanecer sem implementação.

**Independent Test**: Pode ser testado isoladamente construindo um `EvaluationContext` a partir de
um `NormalizedTrace` de exemplo de bot agêntico e a lista de métricas
`AgentStrategy().get_metrics()`, executando o fluxo de avaliação, e verificando que o
`EvaluationResult` resultante contém uma entrada para `task_completion` (score e status
passou/reprovou), sem exigir mudanças em `AgentStrategy`, `MetricFactory` ou
`EvaluationOrchestrator`.

**Acceptance Scenarios**:

1. **Given** um `NormalizedTrace` de um bot agêntico com `input`, `output` e `tools_called`
   preenchidos, **When** a avaliação é executada com a lista de métricas retornada por
   `AgentStrategy.get_metrics()`, **Then** o `EvaluationResult` produzido contém uma entrada para
   `task_completion` com score e status individual, ao lado da entrada já existente para
   `tool_correctness`.
2. **Given** o nome canônico `task_completion` já registrado no `MetricFactory`, **When**
   `MetricFactory.create("task_completion", ...)` é chamado, **Then** uma instância válida é
   retornada, sem exigir nenhuma alteração em `MetricFactory`, `EvaluationOrchestrator`,
   `EvaluationContext` ou `EvaluationResult`.

---

### User Story 2 - Detectar alucinação em respostas de bots RAG (Priority: P2)

Um bot RAG pode gerar uma resposta plausível que contradiz ou inventa informação além do que os
documentos recuperados sustentam — algo que as cinco métricas RAG já implementadas no M3.1
(relevância da resposta, fidelidade, precisão/cobertura/relevância do contexto) não cobrem
explicitamente como um sinal dedicado de "alucinação". Uma `HallucinationMetric` precisa ficar
disponível e passar a rodar automaticamente em toda avaliação de bot RAG.

**Why this priority**: É uma expansão de cobertura sobre um fluxo que já funciona (avaliação RAG
do M3.1), não a correção de um caminho quebrado — por isso vem depois de
`TaskCompletionMetric` (User Story 1), mas ainda é o item central que dá nome à família de
métricas "RAG + Agênticas" desta milestone.

**Independent Test**: Pode ser testado isoladamente construindo um `EvaluationContext` a partir de
um `NormalizedTrace` de exemplo de bot RAG e a lista de métricas `RAGStrategy().get_metrics()`,
executando o fluxo de avaliação, e verificando que o `EvaluationResult` resultante contém uma
entrada para `hallucination` (score e status passou/reprovou) ao lado das cinco métricas RAG já
existentes — sem exigir que o chamador passe `hallucination` explicitamente.

**Acceptance Scenarios**:

1. **Given** um `NormalizedTrace` de um bot RAG normalizado, **When** a avaliação é executada com
   a lista de métricas retornada por `RAGStrategy.get_metrics()`, **Then** o `EvaluationResult`
   produzido contém uma entrada para `hallucination`, além das cinco entradas já produzidas pelas
   métricas RAG do M3.1.
2. **Given** o nome canônico `hallucination` já registrado no `MetricFactory`, **When**
   `MetricFactory.create("hallucination", ...)` é chamado, **Then** uma instância válida é
   retornada, sem exigir nenhuma alteração em `MetricFactory`, `EvaluationOrchestrator`,
   `EvaluationContext` ou `EvaluationResult`.

---

### Edge Cases

- Um `NormalizedTrace` sem os campos mínimos que `hallucination` ou `task_completion` precisam
  (ex.: `tools_called` vazio para `task_completion`) é tratado como reprovação isolada daquela
  métrica específica, com um detalhe descritivo no `EvaluationResult` — o mesmo tratamento de
  falha isolada já estabelecido no M3.1 para as demais métricas, sem exceção não tratada e sem
  bloquear as outras métricas do mesmo trace.
- A adição de `hallucination` a `RAGStrategy.get_metrics()` não deve alterar o comportamento das
  cinco métricas RAG já existentes nessa lista — a lista cresce de cinco para seis nomes; nenhum
  nome existente é removido, reordenado ou tem seu comportamento alterado.
- `ConversationStrategy.get_metrics()` já referencia dois outros nomes sem wrapper registrado
  (`conversation_completeness`, `turn_relevancy`) — esse gap é explicitamente fora do escopo
  desta feature (ver Assumptions) e não deve ser confundido com o gap de `task_completion`
  corrigido aqui.
- Uma métrica cujo `measure()` levanta exceção ou estoura o timeout configurado segue exatamente
  o mesmo tratamento de isolamento por métrica já estabelecido no M3.1 (`score = null`,
  `passed = false`, detalhe do erro) — esta feature não introduz um novo modelo de falha.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST provide a metric wrapper implementing the common `MetricBase` contract
  (M3.1) that wraps DeepEval's native task-completion metric, self-registered in `MetricFactory`
  under the canonical name `task_completion`.
- **FR-002**: System MUST provide a metric wrapper implementing the common `MetricBase` contract
  (M3.1) that wraps DeepEval's native hallucination-detection metric, self-registered in
  `MetricFactory` under the canonical name `hallucination`.
- **FR-003**: The set of metrics automatically evaluated for every RAG bot MUST include
  `hallucination`, alongside the five RAG metrics already produced by this system since M3.1 —
  without requiring any caller to request it explicitly.
- **FR-004**: The set of metrics automatically evaluated for every agentic bot MUST resolve
  `task_completion` successfully — closing the currently-broken reference without requiring any
  change to how agentic bot evaluations are requested.
- **FR-005**: Both new metrics MUST integrate with the evaluation pipeline established in M3.1
  (threshold resolution, timeout handling, concurrent execution, per-metric failure isolation,
  result aggregation) without requiring any change to `MetricFactory`, `EvaluationOrchestrator`,
  `EvaluationContext`, or `EvaluationResult`.
- **FR-006**: System MUST expose score, threshold, pass/fail status, and error detail for both new
  metrics through the same result contract already used by every other registered metric — no new
  or different result schema.
- **FR-007**: `HallucinationMetricWrapper` MUST supply DeepEval's native hallucination metric with
  its required `context` test-case field (sourced from the same `NormalizedTrace.context` data
  already used to populate `retrieval_context`) by overriding test-case construction locally within
  the wrapper itself — without modifying `MetricBase` or any of the six other registered metric
  wrappers.

### Key Entities *(include if feature involves data)*

- **TaskCompletionMetricWrapper**: New `MetricBase` subclass wrapping DeepEval's native
  task-completion metric; closes the metric name `task_completion` already declared as part of
  every agentic bot's evaluation set.
- **HallucinationMetricWrapper**: New `MetricBase` subclass wrapping DeepEval's native
  hallucination-detection metric; adds the metric name `hallucination` to the evaluation set
  already run for every RAG bot. Overrides test-case construction locally to populate the native
  metric's required `context` field from `NormalizedTrace.context` (the same source already used
  for `retrieval_context`), since the shared `MetricBase` construction only populates
  `retrieval_context` and leaves `context` unset. This override is scoped to the wrapper itself —
  `MetricBase` and the six other registered wrappers are unchanged.
- **RAGStrategy** *(modified)*: Existing `EvaluationStrategy` subclass; `get_metrics()` gains the
  additive `"hallucination"` metric name for RAG bots — no other change.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of agentic-bot trace evaluations that include `task_completion` in their
  requested metric set complete and produce a result for it, versus 0% today (every such request
  currently fails before producing any result).
- **SC-002**: 100% of RAG-bot trace evaluations produce a hallucination result alongside the five
  RAG metrics already produced since M3.1, with zero change required to how a RAG bot evaluation
  is requested.
- **SC-003**: A failure or timeout in either new metric never prevents the other metrics evaluated
  for the same trace from completing and reporting their own result.
- **SC-004**: Delivering both metrics requires adding exactly two new metric classes and one
  addition to the RAG bot's metric list — zero modifications to the shared evaluation
  orchestration, factory, or result components already in production since M3.1.

## Assumptions

- `NormalizedTrace` (M2.2) is frozen this milestone — no new fields are added. Both new metrics
  work within the trace-to-test-case field mapping already established in M3.1; a metric whose
  required field has no corresponding `NormalizedTrace` data at all is treated as an isolated
  per-metric failure (same precedent already documented in M3.1 for `tool_correctness`), not a
  blocking defect of this feature. This does not apply to `HallucinationMetric`'s required
  `context` field: the underlying data already exists on `NormalizedTrace.context`, it is simply
  wired to the wrong `LLMTestCase` attribute by the shared mapping — see FR-007, resolved via a
  wrapper-local override rather than an accepted failure.
- DeepEval's native task-completion metric supports an optional task-description input; this
  milestone does not introduce that as new user-facing configuration — the metric is expected to
  evaluate using only the input/output/tool-call signals already available from `NormalizedTrace`.
- `ConversationStrategy`'s two unregistered metric names (`conversation_completeness`,
  `turn_relevancy`) are explicitly out of scope for this milestone — a separate, future concern.
- Threshold and timeout configuration for `hallucination` and `task_completion` follow the exact
  same `ConfigManager`-based resolution and native-default fallback already implemented generically
  by `EvaluationOrchestrator` in M3.1 — no new configuration mechanism is introduced.

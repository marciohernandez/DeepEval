# Feature Specification: MetricFactory + EvaluationStrategy Integration

**Feature Branch**: `004-metric-factory-eval-strategy`

**Created**: 2026-07-13

**Status**: Draft

**Input**: User description: "Módulos em escopo para M3.1 — MetricFactory + EvaluationStrategy:
`MetricBase` (ABC) — interface comum de todas as métricas: `measure(context)`, `threshold`,
`passed`; `EvaluationContext` (dataclass) — entrada: `NormalizedTrace` + config de avaliação;
`EvaluationResult` (dataclass) — saída: scores por métrica, status passed/failed, detalhes;
`MetricFactory` (Factory Method) — registry de métricas; instancia pelo nome; extensível sem
alterar código existente."

## Clarifications

### Session 2026-07-13

- Q: Como o `EvaluationResult` deve agregar o status geral (`passed`/`failed`) a partir dos
  resultados individuais de cada métrica? → A: Todas as métricas devem passar (AND) — o status
  geral é `failed` se qualquer métrica ficar abaixo do seu threshold.
- Q: De onde vem o threshold de cada métrica, dado que a "config de avaliação" é um dos dois
  campos de `EvaluationContext`? → A: Configurável por bot/métrica (lido via `ConfigManager`),
  com fallback para o threshold default nativo da métrica DeepEval quando não configurado.
- Q: O que acontece quando `measure()` de uma métrica levanta exceção (ex.: falha na chamada ao
  LLM juiz)? → A: Isolamento por métrica — a métrica com erro é registrada no `EvaluationResult`
  com o detalhe do erro e conta como reprovada; as demais métricas do mesmo trace continuam
  sendo avaliadas normalmente.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Avaliar um trace com o conjunto de métricas do seu tipo de bot (Priority: P1)

Um trace já normalizado (`NormalizedTrace`, produzido pelo M2.2) e a lista de métricas
declaradas por sua `EvaluationStrategy` (M2.1, ex.: `["answer_relevancy", "faithfulness",
"contextual_precision", "contextual_recall", "contextual_relevancy"]` para RAG) precisam virar
scores concretos: cada métrica nomeada é instanciada, executada contra o trace e o resultado
agregado (score, threshold, passou/reprovou, detalhe) fica disponível para quem pediu a
avaliação — sem que esse chamador precise saber como cada métrica é construída ou configurada.

**Why this priority**: Sem isso, `EvaluationStrategy.get_metrics()` (já implementado no M2.1)
permanece uma lista de nomes sem uso prático — é o elo que faltava entre "que métricas avaliar"
e "os números reais". Nenhuma outra funcionalidade do M3 (test-case construction, dashboards,
relatórios) tem o que consumir sem este elo.

**Independent Test**: Pode ser testado isoladamente construindo um `EvaluationContext` a partir
de um `NormalizedTrace` de exemplo e uma lista fixa de nomes de métricas, chamando o fluxo de
avaliação, e verificando que o `EvaluationResult` resultante contém um score e um status por
métrica pedida — sem depender de dashboards, persistência ou coleta de traces.

**Acceptance Scenarios**:

1. **Given** um `NormalizedTrace` de um bot RAG com `input`, `output`, `context` e
   `expected_output` preenchidos, e a lista de métricas `["answer_relevancy",
   "faithfulness"]`, **When** cada métrica é instanciada pelo nome e executada contra o
   `EvaluationContext`, **Then** o `EvaluationResult` produzido contém um score e um status
   passou/reprovou individual para `answer_relevancy` e para `faithfulness`.
2. **Given** um `EvaluationResult` com múltiplas métricas avaliadas, **When** todas as métricas
   individuais passaram no seu threshold, **Then** o status geral do `EvaluationResult` é
   `passed`.
3. **Given** um `EvaluationResult` com múltiplas métricas avaliadas, **When** ao menos uma
   métrica individual reprova no seu threshold, **Then** o status geral do `EvaluationResult` é
   `failed`, e o(s) detalhe(s) identificam exatamente qual(is) métrica(s) reprovou(aram).

---

### User Story 2 - Adicionar uma métrica nova sem tocar em código existente (Priority: P2)

Uma nova métrica (nativa do DeepEval ou, na ausência de equivalente nativo, uma métrica
customizada seguindo o contrato comum) precisa ficar disponível para qualquer
`EvaluationStrategy` referenciá-la pelo nome, sem exigir alterações em `MetricFactory` além de
um novo registro, e sem exigir alterações em nenhuma métrica já registrada.

**Why this priority**: É o contrato de extensibilidade (Princípio VI da constituição —
Extensibility by Design / Factory Method) que justifica o próprio padrão escolhido para
`MetricFactory`. Sem essa garantia, cada nova métrica viraria uma cadeia de `if/else` espalhada
pelo código de avaliação.

**Independent Test**: Pode ser testado registrando uma métrica de teste (dummy) no registry de
`MetricFactory` e confirmando que ela pode ser instanciada pelo nome e usada em um
`EvaluationContext`, sem qualquer alteração nas métricas pré-existentes ou no código de
`MetricFactory.create()`.

**Acceptance Scenarios**:

1. **Given** uma nova métrica que implementa `MetricBase`, **When** ela é adicionada ao registry
   de `MetricFactory` com um nome canônico único, **Then** `MetricFactory.create(nome)` a
   instancia corretamente sem exigir mudanças em nenhuma métrica já registrada.
2. **Given** um nome de métrica não registrado em `MetricFactory`, **When** `MetricFactory.
   create(nome)` é chamado com esse nome, **Then** o sistema levanta um erro descritivo
   identificando o nome recebido e a lista de nomes suportados — nunca falha silenciosamente ou
   retorna `None`.

---

### User Story 3 - Aplicar threshold configurável por bot/métrica (Priority: P3)

Uma organização quer usar um threshold mais rígido (ex.: `0.8` em vez do default `0.5`) para
`faithfulness` em um bot específico, sem alterar código-fonte — apenas configuração.

**Why this priority**: Cobre o requisito de "Zero Hardcode" (Princípio V) já aplicado a
thresholds pela tabela de configuração da constituição, mas é uma camada de refinamento sobre o
fluxo básico de avaliação (User Story 1), não um bloqueador dele.

**Independent Test**: Pode ser testado configurando um threshold customizado para uma métrica de
um bot específico e confirmando que o `EvaluationResult` dessa métrica usa o threshold
configurado (não o default nativo da métrica) ao decidir passou/reprovou; e testado
separadamente confirmando que, na ausência de configuração, o default nativo da métrica DeepEval
é usado.

**Acceptance Scenarios**:

1. **Given** um threshold customizado configurado para `faithfulness` no bot `test_rag_bot`,
   **When** essa métrica é instanciada via `MetricFactory` dentro de um `EvaluationContext` para
   esse bot, **Then** o threshold aplicado na avaliação é o valor configurado, refletido tanto na
   instância da métrica quanto no `EvaluationResult`.
2. **Given** um bot sem threshold customizado configurado para uma métrica, **When** essa métrica
   é instanciada, **Then** o threshold aplicado é o default nativo daquela métrica no DeepEval.

---

### Edge Cases

- Uma métrica cujo `measure()` levanta exceção (ex.: erro de rede ao chamar o LLM juiz) NÃO deve
  impedir a avaliação das demais métricas do mesmo `EvaluationContext` — o erro é isolado e
  registrado como reprovação nos detalhes daquela métrica específica no `EvaluationResult`.
- Um `EvaluationContext` cujo `NormalizedTrace` não tem os campos mínimos que uma métrica
  precisa (ex.: `faithfulness` exige `context`, mas o trace tem `context` vazio) é tratado como
  reprovação isolada daquela métrica com um detalhe descritivo — não como exceção não tratada.
  (A checagem de campos mínimos por tipo de bot já existe via `ValidationRule`, M2.2; este
  módulo não a duplica, mas precisa se comportar de forma segura quando ela não foi chamada
  antes ou quando uma métrica específica exige mais do que o mínimo por tipo de bot.)
- Uma lista de nomes de métricas vinda de `EvaluationStrategy.get_metrics()` com um nome que não
  está registrado em `MetricFactory` deve gerar um erro descritivo identificando o nome
  desconhecido, não uma falha silenciosa que omite aquela métrica do resultado.
- Um `EvaluationContext` sem nenhuma métrica a avaliar (lista vazia) é uma configuração inválida
  do chamador e deve ser rejeitada com um erro descritivo, não produzir um `EvaluationResult`
  vazio com status `passed` por vacuidade.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: `MetricBase` MUST ser uma interface (ABC) comum a todas as métricas usadas pelo
  sistema, expondo no mínimo: um método `measure(context)` que recebe um `EvaluationContext` e
  produz um resultado de avaliação para aquela métrica; uma propriedade `threshold` (o valor
  mínimo de score para aprovação); e uma propriedade `passed` (se a última execução de
  `measure()` aprovou ou reprovou nesse threshold).
- **FR-002**: Toda métrica nativa do DeepEval usada pelo sistema (`AnswerRelevancyMetric`,
  `FaithfulnessMetric`, `ContextualPrecisionMetric`, `ContextualRecallMetric`,
  `ContextualRelevancyMetric`, `ToolCorrectnessMetric`, e demais métricas referenciadas pelas
  `EvaluationStrategy` existentes) MUST ser usada como motor de scoring por trás de `MetricBase`
  — sem reimplementar a lógica de cálculo de score que o DeepEval já fornece (Princípio II,
  DeepEval-First). `MetricBase` adapta essas métricas nativas ao contrato do projeto
  (`EvaluationContext` → resultado), não as substitui.
- **FR-003**: `EvaluationContext` MUST ser um dataclass expondo exatamente dois campos de
  entrada: um `NormalizedTrace` (M2.2) e a configuração de avaliação aplicável (thresholds por
  métrica, quando declarados) para o bot daquele trace.
- **FR-004**: Configuração de avaliação (thresholds por métrica) referenciada por
  `EvaluationContext` MUST ser lida via `ConfigManager`, a partir de declarações por bot em
  configuração externa (nunca hardcoded em `MetricBase`, `MetricFactory` ou em qualquer métrica
  concreta) — consistente com o Princípio V (Zero Hardcode), que já classifica thresholds como
  configuração de ambiente.
- **FR-005**: Quando uma métrica não tem threshold configurado para o bot do
  `EvaluationContext`, o sistema MUST usar o threshold default nativo daquela métrica no
  DeepEval — nunca falhar por ausência de configuração nem assumir um valor arbitrário do
  projeto.
- **FR-006**: `EvaluationResult` MUST ser um dataclass expondo, no mínimo: os scores individuais
  por métrica avaliada; o status geral `passed`/`failed` do trace avaliado; e detalhes por
  métrica (score, threshold aplicado, e — quando reprovada ou com erro — a razão específica da
  reprovação/erro).
- **FR-007**: O status geral de `EvaluationResult` MUST ser `passed` se, e somente se, todas as
  métricas avaliadas naquele `EvaluationContext` reportarem `passed` individualmente — qualquer
  métrica reprovada ou com erro torna o status geral `failed`.
- **FR-008**: `MetricFactory` MUST implementar o padrão Factory Method: um registry que mapeia
  nomes canônicos de métrica (as mesmas strings retornadas por
  `EvaluationStrategyBase.get_metrics()`, M2.1) para a classe `MetricBase` concreta
  correspondente, instanciando pelo nome sob demanda.
- **FR-009**: Adicionar uma métrica nova a `MetricFactory` MUST exigir apenas um novo registro no
  registry — zero alterações em `MetricFactory.create()`, em `MetricBase`, ou em qualquer métrica
  já registrada (mesmo contrato de extensibilidade já aplicado a `StrategyFactory` no M2.1).
- **FR-010**: `MetricFactory.create()` chamado com um nome de métrica não registrado MUST
  levantar um erro descritivo identificando o nome recebido e a lista de nomes suportados —
  nunca retornar `None` nem instanciar uma métrica default silenciosamente.
- **FR-011**: Quando `measure()` de uma métrica levanta exceção durante a avaliação de um
  `EvaluationContext`, o sistema MUST capturar o erro, registrar essa métrica como reprovada com
  o detalhe do erro em `EvaluationResult`, e continuar avaliando as demais métricas daquele
  mesmo `EvaluationContext` normalmente — um erro isolado nunca aborta a avaliação inteira do
  trace.
- **FR-012**: Um `EvaluationContext` cuja lista de métricas a avaliar está vazia MUST ser
  rejeitado com um erro descritivo antes de produzir qualquer `EvaluationResult` — nunca produzir
  um resultado vazio com status `passed`.

### Key Entities

- **MetricBase**: Interface comum (ABC) que toda métrica usada pelo sistema implementa,
  adaptando o motor de scoring nativo do DeepEval ao contrato do projeto: recebe um
  `EvaluationContext`, expõe `threshold` e `passed`. Implementações concretas envolvem uma
  métrica DeepEval por vez (`AnswerRelevancyMetric`, `FaithfulnessMetric`, etc.).
- **EvaluationContext**: Entrada de uma avaliação de métrica única. Campos: um `NormalizedTrace`
  (M2.2) e a configuração de avaliação aplicável (thresholds por métrica, resolvidos via
  `ConfigManager` para o bot daquele trace).
- **EvaluationResult**: Saída agregada da avaliação de um `NormalizedTrace` contra o conjunto de
  métricas de sua `EvaluationStrategy`. Contém scores por métrica, status geral `passed`/`failed`
  (AND de todas as métricas individuais), e detalhes por métrica (score, threshold aplicado,
  razão de reprovação/erro quando aplicável).
- **MetricFactory**: Factory Method que mapeia nomes canônicos de métrica (os mesmos nomes que
  `EvaluationStrategyBase.get_metrics()` retorna, M2.1) para instâncias concretas de
  `MetricBase`, com threshold já resolvido via configuração (FR-004/FR-005). Fecha o elo entre
  "que métricas avaliar" (M2.1) e "os scores reais" (M3.1).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Para qualquer bot com uma `EvaluationStrategy` e `NormalizedTrace` bem formado,
  avaliar esse trace produz um `EvaluationResult` com um score individual para 100% das métricas
  declaradas por `get_metrics()` daquela estratégia.
- **SC-002**: Adicionar uma métrica nova ao sistema requer editar apenas o registry de
  `MetricFactory` — zero alterações em código de métricas já existentes ou no fluxo de avaliação
  já em produção.
- **SC-003**: Um erro na execução de qualquer métrica individual nunca impede a produção de
  scores para as demais métricas do mesmo trace — 100% de isolamento de falha por métrica.
- **SC-004**: O status geral `passed`/`failed` de um `EvaluationResult` reflete corretamente a
  regra AND sobre todas as métricas individuais em 100% dos casos verificados.
- **SC-005**: Um threshold configurado para um bot/métrica é sempre respeitado na decisão
  passou/reprovou daquela métrica; na ausência de configuração, o default nativo da métrica
  DeepEval é sempre respeitado — 100% dos casos, sem exceção silenciosa.
- **SC-006**: Todos os módulos do M3.1 atingem cobertura de teste ≥ 80%, conforme a ferramenta de
  cobertura padrão do projeto.

## Assumptions

- `EvaluationStrategy`, `EvaluationStrategyBase`, `StrategyFactory` e `BotType` já existem (M2.1,
  `specs/002-coleta-traces/`) e não são alterados por este milestone — `EvaluationStrategyBase.
  get_metrics()` continua responsável apenas por listar nomes canônicos de métrica; a
  instanciação real dessas métricas passa a ser responsabilidade de `MetricFactory` (M3.1),
  exatamente como já documentado no docstring de `EvaluationStrategyBase` ("Metric
  *instantiation* ... is deferred to MetricFactory (M3)").
- `NormalizedTrace` já existe (M2.2, `specs/003-trace-normalizer/`) com seus sete campos
  (`input`, `output`, `context`, `expected_output`, `tools_called`, `messages`, `metadata`) e não
  é alterado por este milestone.
- Configuração de threshold por bot/métrica é adicionada como uma nova seção de configuração
  (ex.: em `bots.yaml` ou `settings.yaml`, lida via `ConfigManager`) — sua chave e formato exatos
  são uma decisão de implementação do plano técnico, não desta especificação.
- Status geral do `EvaluationResult` usa agregação AND (todas as métricas devem passar) — decisão
  confirmada em Clarifications, 2026-07-13.
- Falha isolada por métrica (captura de exceção + registro de erro sem abortar as demais) é o
  comportamento esperado — decisão confirmada em Clarifications, 2026-07-13.
- Este milestone não inclui a construção de `LLMTestCase`/`ConversationalTestCase` do DeepEval a
  partir de `NormalizedTrace` como uma entidade nomeada separadamente — essa conversão é tratada
  como parte da responsabilidade interna de `MetricBase.measure()` ao adaptar `EvaluationContext`
  para o formato que a métrica DeepEval subjacente espera.
- Persistência de `EvaluationResult` (ex.: `EvaluationRepository`) e notificação de observers
  (`ResultPublisher`) estão fora de escopo deste milestone — este milestone entrega apenas a
  produção do `EvaluationResult` em memória.

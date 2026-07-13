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
- Q: Quem orquestra a avaliação completa de um trace — iterar sobre os nomes de métrica de
  `EvaluationStrategy.get_metrics()`, instanciar cada uma via `MetricFactory`, executar
  `measure()`, e agregar tudo em um único `EvaluationResult`? → A: Um novo componente
  orquestrador (nome e desenho a definir no plano técnico) é responsável por essa iteração e
  agregação; `MetricFactory` permanece um Factory Method puro, responsável apenas por instanciar
  métricas pelo nome — nunca por orquestrar avaliações ou agregar resultados.
- Q: Quem chama `ConfigManager` para resolver o threshold por métrica, e em que estado esse dado
  chega ao campo de configuração de `EvaluationContext`? → A: Já resolvido antes de
  `EvaluationContext` existir — o Evaluation Orchestrator chama `ConfigManager` uma vez por
  trace e monta o mapa final `{nome_da_métrica: threshold}` (com o fallback ao default nativo já
  aplicado, FR-005) antes de construir o `EvaluationContext`. `MetricFactory.create()` recebe o
  threshold já pronto e nunca chama `ConfigManager` diretamente, permanecendo desacoplado do
  Singleton.
- Q: Como o Evaluation Orchestrator sabe qual é o bot de um `NormalizedTrace`, necessário para
  resolver a config de threshold por bot (FR-004), já que os sete campos de `NormalizedTrace` não
  incluem `bot_id`? → A: `bot_id` é passado como parâmetro explícito separado ao ponto de entrada
  do Evaluation Orchestrator (ex.: `evaluate(trace, bot_id)`), fornecido por quem já tinha esse
  dado ao normalizar o trace no M2.2 — mesmo padrão já usado por
  `TraceNormalizer.normalize(record, bot_id)`, onde `bot_id` é sempre externo ao objeto de trace.
- Q: FR-003 e a definição de `EvaluationContext` em Key Entities descrevem o campo de configuração
  como um mapa `{nome_da_métrica: threshold}` cobrindo todas as métricas do bot, mas a mesma
  entrada de Key Entities também dizia "Entrada de uma avaliação de métrica única" — as duas
  frases descreviam desenhos diferentes (um `EvaluationContext` por trace vs. um por métrica).
  Qual é o escopo real? → A: Um único `EvaluationContext` por trace, contendo o mapa completo de
  thresholds; esse mesmo objeto é passado a cada chamada `MetricBase.measure()`, e cada métrica lê
  apenas sua própria entrada no mapa pelo nome.
- Q: As chamadas `measure()` de múltiplas métricas de um mesmo `EvaluationContext` (cada uma
  envolvendo uma chamada de rede a um LLM juiz) devem rodar sequencialmente ou em
  paralelo/concorrente? → A: Concorrente — o Evaluation Orchestrator MUST avaliar as métricas de
  um mesmo trace em paralelo para reduzir a latência total, com isolamento de falha por métrica
  (FR-011) preservado independentemente da ordem de conclusão.
- Q: FR-011 cobre métricas cujo `measure()` levanta exceção, mas não cobre o caso de uma chamada
  `measure()` travar/demorar indefinidamente sem nunca levantar erro — o que, com execução
  concorrente (FR-014), poderia bloquear a agregação final do `EvaluationResult` indefinidamente.
  A spec deve exigir um timeout por métrica? → A: Sim — o Evaluation Orchestrator MUST aplicar um
  timeout configurável por chamada `measure()` (via `ConfigManager`, com default do projeto),
  tratando o estouro do timeout como falha isolada daquela métrica (mesmo tratamento de FR-011),
  sem bloquear a agregação das demais.
- Q: Como o `EvaluationResult` deve representar o score de uma métrica que falhou por exceção,
  timeout ou entrada insuficiente? → A: Registrar `score = null`, `passed = false` e o detalhe do
  erro, distinguindo falha operacional de um score real `0.0`.
- Q: Quando `EvaluationStrategy.get_metrics()` contém um nome não registrado, qual deve ser o
  comportamento do Evaluation Orchestrator? → A: Validar todos os nomes antes de iniciar a
  avaliação e abortar o trace inteiro com erro descritivo antes de executar qualquer métrica.
- Q: Qual deve ser o ciclo de vida das instâncias retornadas por `MetricFactory.create()`? → A:
  Criar uma nova instância para cada chamada de `create()`, sem reutilização entre traces.
- Q: Como o orquestrador deve tratar um threshold configurado que não seja numérico ou esteja
  fora do intervalo `0.0–1.0`? → A: Pré-validar todos os thresholds e abortar a avaliação inteira
  antes de executar qualquer métrica.
- Q: Qual deve ser a granularidade da configuração de timeout de `measure()`? → A: Um timeout
  global default, com override opcional por nome canônico de métrica.
- Q: Quando uma métrica falha por exceção ou estoura o timeout (FR-011/FR-015), o Evaluation
  Orchestrator deve tentar executar `measure()` novamente (retry) antes de marcá-la como
  reprovada, ou registrar a falha imediatamente sem nenhuma tentativa adicional? → A: Sem retry —
  qualquer exceção ou timeout marca a métrica como reprovada de imediato, sem nova tentativa.
- Q: Onde deve ser rejeitada uma lista vazia de métricas? → A: O Evaluation Orchestrator rejeita
  `metric_names=[]` antes de construir o `EvaluationContext`.
- Q: Como novas métricas devem entrar no registry? → A: Autorregistro pela subclasse, via
  decorator ou mecanismo equivalente; nenhum arquivo existente é alterado.
- Q: Como o Evaluation Orchestrator deve tratar nomes de métricas duplicados? → A: Rejeitar
  atomicamente a lista e informar todos os nomes duplicados antes de executar métricas.
- Q: O que deve acontecer quando duas subclasses declaram o mesmo nome canônico? → A: Rejeitar
  o segundo registro imediatamente com erro que identifique o nome e ambas as classes.
- Q: Como os detalhes de exceções devem ser expostos no resultado? → A: Retornar categoria/código
  e mensagem sanitizada; detalhes técnicos somente em observabilidade interna com redação de
  segredos.
- Q: Como o Evaluation Orchestrator deve tratar um timeout configurado (default global ou override
  por métrica) que não seja numérico ou seja ≤ 0? → A: Mesmo tratamento do threshold inválido —
  pré-validar atomicamente todos os timeouts (default global + overrides) antes de construir o
  `EvaluationContext`; se algum for não-numérico ou ≤ 0, abortar a avaliação inteira com erro que
  liste cada valor inválido, mesmo padrão já adotado para thresholds em FR-005.
- Q: Quando o Evaluation Orchestrator chama `ConfigManager` para resolver thresholds/timeouts de
  um `bot_id` e `ConfigManager` levanta uma exceção (ex.: falha ao ler configuração), qual deve
  ser o comportamento? → A: Mesmo tratamento de um valor de configuração inválido — abortar a
  avaliação inteira do trace com erro descritivo antes de construir o `EvaluationContext` ou
  executar qualquer métrica; fail-closed, sem fallback para defaults nativos nem execução parcial.
- Q: Quando `bot_id` não tem nenhuma entrada de configuração em `ConfigManager` (bot
  desconhecido), como o Evaluation Orchestrator deve se comportar? → A: Tratar como "nada
  configurado" — aplicar o threshold e o timeout default nativos para todas as métricas, exatamente
  o mesmo fallback por ausência de configuração já usado por métrica individual (FR-005/FR-015);
  `bot_id` desconhecido não é uma classe de erro distinta, não aborta a avaliação.
- Q: Deve haver um limite máximo de concorrência para as chamadas `measure()` paralelas de um
  mesmo trace, ou todas as métricas de um `EvaluationContext` rodam em paralelo sem limite? → A:
  Sem limite neste milestone — todas as métricas de um trace rodam totalmente em paralelo; não há
  cap de concorrência em escopo (listas de métricas por bot são tipicamente pequenas, e o timeout
  por métrica de FR-015 já limita quanto tempo cada chamada pode ocupar).

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
`EvaluationStrategy` referenciá-la pelo nome mediante autorregistro declarado na própria nova
subclasse, sem exigir alterações em `MetricFactory`, em um registry central ou em qualquer
métrica já registrada.

**Why this priority**: É o contrato de extensibilidade (Princípio VI da constituição —
Extensibility by Design / Factory Method) que justifica o próprio padrão escolhido para
`MetricFactory`. Sem essa garantia, cada nova métrica viraria uma cadeia de `if/else` espalhada
pelo código de avaliação.

**Independent Test**: Pode ser testado definindo uma nova métrica de teste (dummy) com sua
declaração de autorregistro e confirmando que ela pode ser instanciada pelo nome e usada em um
`EvaluationContext`, sem qualquer alteração em arquivos pré-existentes ou no código de
`MetricFactory`.

**Acceptance Scenarios**:

1. **Given** uma nova métrica que implementa `MetricBase` e declara seu nome canônico único pelo
   mecanismo de autorregistro, **When** sua classe fica disponível ao sistema, **Then**
   `MetricFactory.create(nome)` a instancia corretamente sem exigir mudanças em nenhum arquivo
   pré-existente.
2. **Given** um nome de métrica não registrado em `MetricFactory`, **When** `MetricFactory.
   create(nome)` é chamado com esse nome, **Then** o sistema levanta um erro descritivo
   identificando o nome recebido e a lista de nomes suportados — nunca falha silenciosamente ou
   retorna `None`.
3. **Given** uma classe de métrica já registrada sob um nome canônico, **When** outra subclasse
   tenta se autorregistrar com o mesmo nome, **Then** o segundo registro é rejeitado imediatamente
   com erro que identifica o nome em colisão e ambas as classes, sem substituir ou ignorar
   silenciosamente qualquer implementação.

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
  registrado como reprovação nos detalhes daquela métrica específica no `EvaluationResult`. O
  detalhe público contém categoria/código e mensagem sanitizada; mensagens brutas, credenciais,
  payloads e outros dados sensíveis não são propagados ao resultado.
- Um `EvaluationContext` cujo `NormalizedTrace` não tem os campos mínimos que uma métrica
  precisa (ex.: `faithfulness` exige `context`, mas o trace tem `context` vazio) é tratado como
  reprovação isolada daquela métrica com um detalhe descritivo — não como exceção não tratada.
  (A checagem de campos mínimos por tipo de bot já existe via `ValidationRule`, M2.2; este
  módulo não a duplica, mas precisa se comportar de forma segura quando ela não foi chamada
  antes ou quando uma métrica específica exige mais do que o mínimo por tipo de bot.)
- Uma lista de nomes de métricas vinda de `EvaluationStrategy.get_metrics()` com um nome que não
  está registrado em `MetricFactory` deve ser rejeitada integralmente antes da construção do
  `EvaluationContext` e antes de qualquer chamada `measure()`. O erro deve identificar todos os
  nomes desconhecidos e os nomes suportados; nenhuma métrica válida da lista é executada e
  nenhum `EvaluationResult` parcial é produzido.
- Uma lista vazia de nomes de métricas (`metric_names=[]`) é uma configuração inválida do
  chamador e deve ser rejeitada pelo Evaluation Orchestrator antes de construir o
  `EvaluationContext`, não produzir um `EvaluationResult` vazio com status `passed` por
  vacuidade.
- Uma lista de nomes de métricas com duplicatas é uma configuração inválida e deve ser rejeitada
  atomicamente pelo Evaluation Orchestrator antes de construir o `EvaluationContext` ou executar
  qualquer métrica. O erro identifica todos os nomes duplicados; o sistema não remove duplicatas
  silenciosamente nem sobrescreve entradas no `EvaluationResult`.
- Duas subclasses de `MetricBase` que declaram o mesmo nome canônico constituem uma colisão de
  registro. A segunda tentativa de registro é rejeitada imediatamente com erro que identifica o
  nome e ambas as classes; a implementação existente nunca é substituída e a nova nunca é
  ignorada silenciosamente.
- Uma métrica cujo `measure()` excede o timeout configurado (ex.: LLM juiz sem resposta) NÃO deve
  bloquear a avaliação das demais métricas concorrentes do mesmo `EvaluationContext` nem a
  agregação final do `EvaluationResult` — o estouro é tratado como falha isolada daquela métrica,
  com o mesmo tratamento dado a uma exceção (FR-011/FR-015). Nem a exceção nem o estouro de
  timeout disparam uma nova tentativa (retry) de `measure()` para essa métrica — a primeira falha
  já é definitiva para aquela avaliação.
- Uma métrica que falha por exceção, timeout ou entrada insuficiente permanece presente no
  `EvaluationResult` com `score = null`, `passed = false` e o detalhe do erro; `null` nunca é
  convertido em `0.0`, pois falha operacional não equivale a um score real zero.
- Um threshold explicitamente configurado que não seja numérico ou esteja fora do intervalo
  inclusivo `0.0–1.0` invalida a configuração do trace inteiro. O Evaluation Orchestrator deve
  identificar todos os valores inválidos e abortar antes de construir o `EvaluationContext` ou
  executar qualquer métrica; não aplica fallback, arredondamento ou resultado parcial.
- Um timeout configurado (default global ou override por nome canônico de métrica) que não seja
  numérico ou seja ≤ 0 invalida a configuração do trace inteiro, com o mesmo tratamento dado a um
  threshold inválido: o Evaluation Orchestrator identifica todos os valores de timeout inválidos e
  aborta antes de construir o `EvaluationContext` ou executar qualquer métrica; não aplica
  fallback, ajuste automático ou resultado parcial.
- Uma falha do próprio `ConfigManager` (ex.: exceção ao ler configuração) durante a resolução de
  thresholds ou timeouts para um `bot_id` é tratada como uma configuração inválida do trace
  inteiro: o Evaluation Orchestrator aborta a avaliação antes de construir o `EvaluationContext`
  ou executar qualquer métrica, com erro descritivo — fail-closed, sem fallback para defaults
  nativos nem execução parcial.
- Um `bot_id` sem nenhuma entrada de configuração em `ConfigManager` (bot desconhecido) NÃO é uma
  classe de erro distinta — é tratado exatamente como "nenhum threshold/timeout configurado" para
  cada métrica: o Evaluation Orchestrator aplica os defaults nativos de threshold e timeout para
  todas as métricas daquele trace e prossegue normalmente, sem abortar a avaliação.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: `MetricBase` MUST ser uma interface (ABC) comum a todas as métricas usadas pelo
  sistema, expondo no mínimo: um método `measure(context)` que recebe um `EvaluationContext` e
  produz um resultado de avaliação para aquela métrica; uma propriedade `threshold` (o valor
  mínimo de score para aprovação); e uma propriedade `passed` (se a última execução de
  `measure()` aprovou ou reprovou nesse threshold).
- **FR-002**: Toda métrica nativa do DeepEval usada pelo sistema (`AnswerRelevancyMetric`,
  `FaithfulnessMetric`, `ContextualPrecisionMetric`, `ContextualRecallMetric`,
  `ContextualRelevancyMetric`, `ToolCorrectnessMetric`) MUST ser usada como motor de scoring por
  trás de `MetricBase` — sem reimplementar a lógica de cálculo de score que o DeepEval já fornece
  (Princípio II, DeepEval-First). `MetricBase` adapta essas métricas nativas ao contrato do
  projeto (`EvaluationContext` → resultado), não as substitui. Este milestone cobre exatamente as
  cinco métricas de `RAGStrategy` mais `tool_correctness` (a métrica de `AgentStrategy` coberta
  nesta fase); `task_completion` (`AgentStrategy`) e `conversation_completeness`/
  `turn_relevancy` (`ConversationStrategy`) ficam fora do escopo do M3.1 (ver Assumptions).
- **FR-003**: `EvaluationContext` MUST ser um dataclass expondo exatamente dois campos de
  entrada: um `NormalizedTrace` (M2.2) e a configuração de avaliação aplicável (thresholds por
  métrica, quando declarados) para o bot daquele trace.
- **FR-004**: Configuração de avaliação (thresholds por métrica) referenciada por
  `EvaluationContext` MUST ser lida via `ConfigManager`, a partir de declarações por bot em
  configuração externa (nunca hardcoded em `MetricBase`, `MetricFactory` ou em qualquer métrica
  concreta) — consistente com o Princípio V (Zero Hardcode), que já classifica thresholds como
  configuração de ambiente. Essa leitura MUST ser feita pelo Evaluation Orchestrator (FR-013),
  que resolve o mapa `{nome_da_métrica: threshold}` uma única vez por trace e o entrega já pronto
  ao construir o `EvaluationContext`; `MetricFactory` MUST NUNCA chamar `ConfigManager`
  diretamente. Como `NormalizedTrace` não carrega identificador de bot entre seus sete campos, o
  Evaluation Orchestrator MUST receber `bot_id` como parâmetro explícito separado em seu ponto de
  entrada (mesmo padrão já usado por `TraceNormalizer.normalize(record, bot_id)` no M2.2) —
  `bot_id` nunca é inferido de dentro do `NormalizedTrace`. Se a própria chamada a `ConfigManager`
  levantar uma exceção (ex.: falha ao ler configuração) durante essa resolução, o Evaluation
  Orchestrator MUST tratar isso como uma configuração inválida do trace inteiro e abortar a
  avaliação com erro descritivo antes de construir o `EvaluationContext` ou executar qualquer
  métrica — fail-closed, sem fallback para os defaults nativos nem execução parcial.
- **FR-005**: Quando uma métrica não tem threshold configurado para o bot do
  `EvaluationContext` — incluindo o caso de `bot_id` não ter nenhuma entrada de configuração em
  `ConfigManager` — o Evaluation Orchestrator MUST aplicar o threshold default nativo daquela
  métrica no DeepEval ao montar o mapa de thresholds — nunca falhar por ausência de configuração
  nem assumir um valor arbitrário do projeto; um `bot_id` desconhecido em `ConfigManager` não é
  tratado como erro, apenas como ausência de configuração para todas as suas métricas. Todo
  threshold explicitamente configurado MUST ser
  numérico e pertencer ao intervalo inclusivo `0.0–1.0`; antes de construir o
  `EvaluationContext`, o Evaluation Orchestrator MUST validar atomicamente todos os valores
  configurados e, se algum for inválido, abortar a avaliação inteira com erro que liste cada
  métrica e valor inválido, sem fallback, ajuste automático ou execução parcial.
- **FR-006**: `EvaluationResult` MUST ser um dataclass expondo, no mínimo: os scores individuais
  por métrica avaliada; o status geral `passed`/`failed` do trace avaliado; e detalhes por
  métrica (score, threshold aplicado, e — quando reprovada ou com erro — a razão específica da
  reprovação/erro). Para uma métrica que falha por exceção, timeout ou entrada insuficiente, o
  score MUST ser `null`, o status individual MUST ser `failed`, e o detalhe MUST registrar a
  razão por meio de categoria/código e mensagem sanitizada; o sistema MUST NUNCA converter essa
  falha em um score real `0.0` nem incluir mensagem bruta de exceção, credencial, payload ou outro
  dado sensível no resultado.
- **FR-007**: O status geral de `EvaluationResult` MUST ser `passed` se, e somente se, todas as
  métricas avaliadas naquele `EvaluationContext` reportarem `passed` individualmente — qualquer
  métrica reprovada ou com erro torna o status geral `failed`.
- **FR-008**: `MetricFactory` MUST implementar o padrão Factory Method: um registry que mapeia
  nomes canônicos de métrica (as mesmas strings retornadas por
  `EvaluationStrategyBase.get_metrics()`, M2.1) para a classe `MetricBase` concreta
  correspondente, instanciando pelo nome sob demanda. Cada chamada de `create()` MUST retornar
  uma instância nova; instâncias de `MetricBase` MUST NUNCA ser compartilhadas ou reutilizadas
  entre traces, pois `threshold` e `passed` representam estado daquela execução.
- **FR-009**: Adicionar uma métrica nova ao sistema MUST exigir apenas criar sua subclasse de
  `MetricBase`, que declara o próprio nome canônico e se autorregistra via decorator ou mecanismo
  equivalente — zero alterações em `MetricFactory`, `MetricBase`, registry central ou qualquer
  arquivo pré-existente (contrato de extensibilidade exigido pelo Princípio VI da constituição;
  `MetricFactory` introduz o primeiro registro por decorator do projeto — `StrategyFactory` do
  M2.1 usa um dict hardcoded em seu próprio código-fonte, um mecanismo diferente que ainda exige
  editar o arquivo da factory para cada nova entrada). Se uma segunda subclasse tentar registrar um
  nome canônico já existente, o registro MUST falhar imediatamente com erro que identifique o
  nome e ambas as classes; sobrescrever ou ignorar silenciosamente um registro é proibido.
- **FR-010**: `MetricFactory.create()` chamado com um nome de métrica não registrado MUST
  levantar um erro descritivo identificando o nome recebido e a lista de nomes suportados —
  nunca retornar `None` nem instanciar uma métrica default silenciosamente. Antes de construir o
  `EvaluationContext` ou executar qualquer métrica, o Evaluation Orchestrator MUST pré-validar
  atomicamente a lista completa: todos os nomes devem estar registrados e devem ser únicos. Se
  houver nomes desconhecidos ou duplicados, MUST abortar a avaliação inteira com um único erro
  que liste todos os problemas encontrados e os nomes suportados, sem remover duplicatas, sem
  executar métricas válidas e sem produzir resultado parcial.
- **FR-011**: Quando `measure()` de uma métrica levanta exceção durante a avaliação de um
  `EvaluationContext`, o sistema MUST capturar o erro, registrar essa métrica como reprovada com
  o detalhe sanitizado do erro em `EvaluationResult`, e continuar avaliando as demais métricas
  daquele mesmo `EvaluationContext` normalmente — um erro isolado nunca aborta a avaliação
  inteira do trace. Detalhes técnicos adicionais MAY ser enviados à observabilidade interna
  somente após redação de segredos e dados sensíveis. O sistema MUST NUNCA tentar executar
  `measure()` novamente (retry) para essa métrica — a primeira exceção já marca a métrica como
  reprovada de forma definitiva para aquela avaliação.
- **FR-012**: O Evaluation Orchestrator MUST rejeitar uma lista vazia de nomes de métricas com um
  erro descritivo antes de construir o `EvaluationContext` ou produzir qualquer
  `EvaluationResult` — nunca produzir um resultado vazio com status `passed`.
- **FR-013**: A avaliação completa de um `NormalizedTrace` contra a lista de métricas de sua
  `EvaluationStrategy` (construir o único `EvaluationContext` daquele trace, instanciar cada métrica via
  `MetricFactory.create()`, executar `measure()`, e agregar os resultados individuais em um único
  `EvaluationResult`) MUST ser responsabilidade de um componente orquestrador distinto de
  `MetricFactory`. `MetricFactory` MUST permanecer limitado à instanciação de métricas pelo nome
  (Factory Method) — sem lógica de iteração sobre múltiplas métricas ou de agregação de
  resultados.
- **FR-014**: O Evaluation Orchestrator MUST executar as chamadas `measure()` das múltiplas
  métricas de um mesmo `EvaluationContext` em paralelo/concorrente (não sequencialmente), para
  reduzir a latência total da avaliação de um trace — cada chamada de LLM juiz é uma operação de
  rede independente. O isolamento de falha por métrica (FR-011) e a agregação AND do status geral
  (FR-007) MUST se comportar de forma idêntica independentemente da ordem em que as chamadas
  concorrentes terminam. Este milestone NÃO exige um limite máximo de concorrência entre as
  chamadas `measure()` de um mesmo trace — todas as métricas do `EvaluationContext` MAY rodar
  totalmente em paralelo, sem cap.
- **FR-015**: O Evaluation Orchestrator MUST aplicar um timeout configurável (lido via
  `ConfigManager`) a cada chamada `measure()` individual. A configuração MUST oferecer um timeout
  global default obrigatório e MAY oferecer override por nome canônico de métrica; quando houver
  override para a métrica avaliada, ele prevalece sobre o default global. Não há override por bot
  ou por combinação bot/métrica neste milestone. Todo valor de timeout (default global e cada
  override por métrica) MUST ser numérico e maior que zero; antes de construir o
  `EvaluationContext`, o Evaluation Orchestrator MUST validar atomicamente todos os valores de
  timeout configurados junto com os thresholds (FR-005) e, se algum for não-numérico ou ≤ 0,
  abortar a avaliação inteira com erro que liste cada valor de timeout inválido, sem fallback,
  ajuste automático ou execução parcial — mesmo tratamento dado a um threshold inválido. Quando
  uma métrica excede o timeout efetivo, o Evaluation Orchestrator MUST tratar o estouro como uma
  falha isolada daquela métrica — mesmo tratamento dado a uma exceção (FR-011): registrada como
  reprovada com o detalhe do estouro em `EvaluationResult`, sem bloquear a avaliação nem a
  agregação das demais métricas do mesmo trace. Assim como no caso de exceção (FR-011), o sistema
  MUST NUNCA tentar novamente (retry) uma métrica que estourou o timeout — o primeiro estouro já
  marca a métrica como reprovada de forma definitiva.

### Key Entities

- **MetricBase**: Interface comum (ABC) que toda métrica usada pelo sistema implementa,
  adaptando o motor de scoring nativo do DeepEval ao contrato do projeto: recebe um
  `EvaluationContext`, expõe `threshold` e `passed`. Implementações concretas envolvem uma
  métrica DeepEval por vez (`AnswerRelevancyMetric`, `FaithfulnessMetric`, etc.).
- **EvaluationContext**: Entrada de uma avaliação completa de trace — um único `EvaluationContext`
  é construído por trace, não um por métrica. Campos: um `NormalizedTrace` (M2.2) e a configuração
  de avaliação aplicável — um mapa `{nome_da_métrica: threshold}` já resolvido pelo Evaluation
  Orchestrator via `ConfigManager` (com fallback ao default nativo já aplicado) antes da
  construção do `EvaluationContext`; nem `EvaluationContext` nem `MetricFactory` chamam
  `ConfigManager` diretamente. Esse mesmo objeto é passado, sem modificação, a cada chamada
  `MetricBase.measure()` durante a avaliação daquele trace; cada métrica lê apenas sua própria
  entrada no mapa de thresholds pelo nome.
- **EvaluationResult**: Saída agregada da avaliação de um `NormalizedTrace` contra o conjunto de
  métricas de sua `EvaluationStrategy`. Contém scores por métrica, status geral `passed`/`failed`
  (AND de todas as métricas individuais), e detalhes por métrica (score, threshold aplicado,
  razão de reprovação/erro quando aplicável). O score é anulável: vale `null` quando a métrica
  falha por exceção, timeout ou entrada insuficiente, sempre acompanhado de `passed = false` e
  detalhe do erro; um score real `0.0` permanece semanticamente distinto.
- **MetricFactory**: Factory Method que mapeia nomes canônicos de métrica (os mesmos nomes que
  `EvaluationStrategyBase.get_metrics()` retorna, M2.1) para instâncias concretas de
  `MetricBase`, aplicando o threshold já resolvido que recebe pronto do `EvaluationContext`
  (FR-004/FR-005) — nunca chama `ConfigManager` diretamente. Fecha o elo entre "que métricas
  avaliar" (M2.1) e "os scores reais" (M3.1). Responsabilidade estritamente limitada à
  instanciação por nome — nunca itera sobre múltiplas métricas nem agrega resultados (FR-013).
  Cada chamada de `create()` produz uma instância nova e isolada; o registry armazena classes ou
  construtores, nunca instâncias mutáveis compartilhadas. Cada subclasse declara seu nome
  canônico e se autorregistra via decorator ou mecanismo equivalente, de modo que adicionar uma
  métrica não exige editar `MetricFactory` nem um registry central.
- **Evaluation Orchestrator** (nome definitivo a decidir no plano técnico): Componente distinto de
  `MetricFactory`, responsável por, dado um `NormalizedTrace`, um `bot_id` (parâmetro explícito
  separado — `NormalizedTrace` não carrega identificador de bot) e a lista de nomes de métrica de
  `EvaluationStrategy.get_metrics()`: (1) rejeitar uma lista vazia antes de construir o
  `EvaluationContext`; (2) pré-validar atomicamente que todos os nomes estejam registrados e
  sejam únicos, abortando antes de qualquer chamada de métrica e informando todos os nomes
  desconhecidos ou duplicados; (3)
  resolver via `ConfigManager` o mapa
  `{nome_da_métrica: threshold}` para aquele `bot_id`, aplicando o default nativo da métrica
  quando não configurado e validando atomicamente todos os valores explicitamente configurados
  antes de prosseguir (FR-004/FR-005); (4) resolver via `ConfigManager` o timeout global default e
  quaisquer overrides por nome canônico de métrica, validando atomicamente que todos os valores de
  timeout são numéricos e > 0 antes de prosseguir — mesmo tratamento de FR-015; (5) construir o
  único `EvaluationContext` daquele trace com o mapa de thresholds já pronto; (6) chamar
  `MetricFactory.create()` para cada métrica; (7) executar `measure()` de todas as métricas em
  paralelo/concorrente, cada uma sob o override de timeout de seu nome canônico quando declarado,
  ou sob o timeout global default nos demais casos (FR-014/FR-015); e (8) agregar os resultados
  individuais em um único `EvaluationResult`
  (aplicando a regra AND de status geral, FR-007, o isolamento de falha por métrica, FR-011, e o
  isolamento de estouro de timeout, FR-015) — a agregação MUST produzir o mesmo resultado
  independentemente da ordem em que as chamadas concorrentes terminam.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Para qualquer bot cuja `EvaluationStrategy` declare exclusivamente métricas cobertas
  por este milestone (FR-002 — as cinco métricas de `RAGStrategy` mais `tool_correctness`),
  avaliar um `NormalizedTrace` produz um `EvaluationResult` com uma entrada individual para 100%
  das métricas declaradas por `get_metrics()` daquela estratégia: score numérico quando a métrica
  conclui, ou `score = null`, `passed = false` e detalhe do erro quando falha por exceção, timeout
  ou entrada insuficiente. Bots cuja `EvaluationStrategy` declare `task_completion`,
  `conversation_completeness` ou `turn_relevancy` estão fora do escopo deste milestone (ver
  Assumptions) e não são cobertos por este critério.
- **SC-002**: Adicionar uma métrica nova ao sistema requer somente criar a nova subclasse com sua
  declaração de autorregistro — zero alterações em qualquer arquivo existente, incluindo
  `MetricFactory`, `MetricBase`, métricas existentes e o fluxo de avaliação em produção.
- **SC-003**: Um erro na execução de qualquer métrica individual (exceção ou estouro de timeout)
  nunca impede a produção de scores para as demais métricas do mesmo trace — 100% de isolamento
  de falha por métrica, independentemente da ordem de conclusão das chamadas concorrentes.
- **SC-004**: O status geral `passed`/`failed` de um `EvaluationResult` reflete corretamente a
  regra AND sobre todas as métricas individuais em 100% dos casos verificados.
- **SC-005**: Um threshold configurado para um bot/métrica é sempre respeitado na decisão
  passou/reprovou daquela métrica; na ausência de configuração, o default nativo da métrica
  DeepEval é sempre respeitado — 100% dos casos, sem exceção silenciosa.
- **SC-006**: Todos os módulos do M3.1 atingem cobertura de teste ≥ 80%, conforme a ferramenta de
  cobertura padrão do projeto.
- **SC-007**: Em 100% dos casos, qualquer threshold explicitamente configurado que não seja
  numérico ou esteja fora do intervalo inclusivo `0.0–1.0` é rejeitado antes da execução da
  primeira métrica, sem fallback, ajuste automático, chamada parcial ou `EvaluationResult`.
- **SC-008**: Em 100% das falhas por exceção verificadas, o `EvaluationResult` contém uma
  categoria/código e mensagem sanitizada úteis para diagnóstico, sem expor mensagens brutas,
  credenciais, payloads ou outros dados sensíveis; qualquer detalhe técnico enviado à
  observabilidade interna também passa por redação.

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
- A iteração sobre múltiplas métricas e a agregação em `EvaluationResult` são responsabilidade de
  um componente orquestrador distinto de `MetricFactory` (nome definitivo a decidir no plano
  técnico); `MetricFactory` permanece um Factory Method puro (apenas instanciação) — decisão
  confirmada em Clarifications, 2026-07-13.
- A resolução do threshold por métrica via `ConfigManager` (incluindo o fallback ao default
  nativo) acontece uma única vez por trace, dentro do Evaluation Orchestrator, antes da
  construção do `EvaluationContext`; `MetricFactory` nunca chama `ConfigManager` diretamente —
  decisão confirmada em Clarifications, 2026-07-13.
- `bot_id` é recebido pelo Evaluation Orchestrator como parâmetro explícito separado do
  `NormalizedTrace` (que não carrega identificador de bot entre seus sete campos) — mesmo padrão
  já usado por `TraceNormalizer.normalize(record, bot_id)` no M2.2 — decisão confirmada em
  Clarifications, 2026-07-13.
- Um único `EvaluationContext` é construído por trace (não um por métrica), contendo o mapa
  completo de thresholds; esse mesmo objeto é reutilizado, sem modificação, em todas as chamadas
  `MetricBase.measure()` daquele trace — decisão confirmada em Clarifications, 2026-07-13.
- O Evaluation Orchestrator pré-valida atomicamente a lista completa de nomes de métrica antes de
  construir o `EvaluationContext` ou chamar qualquer `measure()`; qualquer nome desconhecido ou
  duplicado aborta a avaliação inteira com erro descritivo que lista todos os problemas, sem
  execução parcial nem remoção silenciosa de duplicatas — decisão confirmada em Clarifications,
  2026-07-13.
- `MetricFactory.create()` retorna uma instância nova em toda chamada; nenhuma instância de
  `MetricBase` é reutilizada entre traces, evitando vazamento de `threshold`/`passed` e condições
  de corrida — decisão confirmada em Clarifications, 2026-07-13.
- Cada nova subclasse de `MetricBase` declara seu nome canônico e se autorregistra via decorator
  ou mecanismo equivalente; não existe registry central que precise ser editado para extensões —
  decisão confirmada em Clarifications, 2026-07-13. Uma colisão de nome canônico rejeita o
  segundo registro imediatamente e identifica ambas as classes, sem comportamento dependente da
  ordem de importação.
- Thresholds explicitamente configurados aceitam apenas valores numéricos no intervalo inclusivo
  `0.0–1.0`; o conjunto inteiro é pré-validado e qualquer valor inválido aborta a avaliação antes
  de chamadas de métricas, sem fallback ou ajuste — decisão confirmada em Clarifications,
  2026-07-13.
- As chamadas `measure()` das métricas de um mesmo `EvaluationContext` rodam em
  paralelo/concorrente (não sequencialmente), para reduzir a latência total da avaliação de um
  trace — decisão confirmada em Clarifications, 2026-07-13.
- Cada chamada `measure()` individual é sujeita a um timeout configurável via `ConfigManager` (com
  um timeout global default obrigatório e override opcional por nome canônico de métrica); o
  override prevalece sobre o default quando presente, e não há override por bot neste milestone.
  O estouro do timeout efetivo é tratado como falha isolada daquela métrica, mesmo tratamento dado
  a uma exceção — decisão confirmada em Clarifications, 2026-07-13. Os valores exatos dos timeouts
  são decisões de implementação do plano técnico, não desta especificação. Todo valor de timeout
  configurado (default global ou override por métrica) deve ser numérico e > 0; o conjunto inteiro
  é pré-validado atomicamente junto com os thresholds, e qualquer valor inválido aborta a avaliação
  antes de chamadas de métricas, sem fallback ou ajuste — decisão confirmada em Clarifications,
  2026-07-13.
- Nenhuma métrica é reexecutada (retry) após falhar por exceção ou timeout — a primeira falha já
  marca a métrica como reprovada de forma definitiva para aquela avaliação, sem tentativa
  adicional — decisão confirmada em Clarifications, 2026-07-13.
- Erros de métricas são expostos no `EvaluationResult` como categoria/código e mensagem
  sanitizada; detalhes técnicos ficam restritos à observabilidade interna e passam por redação de
  segredos e dados sensíveis — decisão confirmada em Clarifications, 2026-07-13.
- Este milestone não inclui a construção de `LLMTestCase`/`ConversationalTestCase` do DeepEval a
  partir de `NormalizedTrace` como uma entidade nomeada separadamente — essa conversão é tratada
  como parte da responsabilidade interna de `MetricBase.measure()` ao adaptar `EvaluationContext`
  para o formato que a métrica DeepEval subjacente espera.
- Persistência de `EvaluationResult` (ex.: `EvaluationRepository`) e notificação de observers
  (`ResultPublisher`) estão fora de escopo deste milestone — este milestone entrega apenas a
  produção do `EvaluationResult` em memória.
- Uma falha do próprio `ConfigManager` (exceção ao resolver thresholds/timeouts para um `bot_id`)
  recebe o mesmo tratamento fail-closed de um valor de configuração inválido — aborta a avaliação
  inteira do trace antes de construir o `EvaluationContext`, sem fallback para defaults nativos —
  decisão confirmada em Clarifications, 2026-07-13.
- Um `bot_id` sem nenhuma entrada de configuração em `ConfigManager` não é um erro — é tratado
  como ausência de configuração para todas as métricas daquele bot, aplicando os defaults nativos
  de threshold e timeout normalmente (mesmo caminho do fallback por métrica de FR-005/FR-015) —
  decisão confirmada em Clarifications, 2026-07-13.
- Não há limite máximo de concorrência entre as chamadas `measure()` de métricas de um mesmo
  trace neste milestone — todas rodam totalmente em paralelo; listas de métricas por bot são
  tipicamente pequenas e o timeout por métrica (FR-015) já limita a duração de cada chamada —
  decisão confirmada em Clarifications, 2026-07-13.
- Este milestone cobre apenas as métricas nomeadas em FR-002: as cinco métricas de `RAGStrategy`
  (`answer_relevancy`, `faithfulness`, `contextual_precision`, `contextual_recall`,
  `contextual_relevancy`) e `tool_correctness` de `AgentStrategy`. `task_completion`
  (`AgentStrategy`) e `conversation_completeness`/`turn_relevancy` (`ConversationStrategy`) — já
  existentes e inalteradas desde o M2.1 — ficam fora do escopo do M3.1; bots avaliados por essas
  estratégias não têm cobertura completa de `MetricFactory` até uma milestone futura. Análise
  registrada em `/speckit-analyze` (finding E1, 2026-07-13).
- `ToolCorrectnessMetric` exige `expected_tools`, campo que `NormalizedTrace` (M2.2, sete campos,
  inalterado por este milestone) não carrega. Como consequência conhecida e aceita neste
  milestone, `tool_correctness.measure()` sempre levanta `MissingTestCaseParamsError` e sempre cai
  no branch de falha isolada de FR-011 (`score = null`, `passed = false`) — nunca produz um score
  real em M3.1; isso não é um defeito do wrapper, mas uma limitação de dados de entrada a ser
  resolvida em um follow-up do M2.2 que adicione `expected_tools` a `NormalizedTrace`. Análise
  registrada em `/speckit-analyze` (finding C1, 2026-07-13).

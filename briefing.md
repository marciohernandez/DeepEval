# Briefing – Sistema de Avaliação de Chatbots com DeepEval

**Projeto:** DeepEval Chatbot Evaluator  
**Data:** 2026-06-19  
**Responsável:** Marcio  

---

## 1. Contexto e Problema

Marcio desenvolve múltiplos chatbots para diferentes finalidades (internos e/ou para clientes). À medida que o número de bots cresce, surge um problema: **não existe um processo sistemático e automatizado para garantir a qualidade das respostas** desses bots.

Sem um sistema de avaliação:
- Regressões de qualidade só são percebidas quando usuários reclamam
- Não há dados objetivos para comparar versões do mesmo bot
- Cada bot é testado de forma manual, inconsistente e não escalável
- Não é possível saber se um bot novo está pronto para produção com confiança

---

## 2. Solução

Desenvolver um **sistema centralizado de avaliação de qualidade de chatbots** que:

1. **Monitora continuamente** as conversas reais em produção (via traces do Langfuse)
2. **Testa automaticamente** antes de cada deploy (CI/CD com datasets fixos)
3. **Avalia múltiplos bots** com métricas configuráveis por bot
4. **Apresenta os resultados** em um dashboard visual para toda a equipe técnica
5. **É extensível** — arquitetura orientada a objetos que cresce sem refatoração

---

## 3. Usuários e Autenticação

| Perfil | Uso |
|--------|-----|
| Marcio (lead dev) | Configura bots, define métricas, analisa resultados, toma decisões de deploy |
| Equipe técnica | Acessa o sistema para acompanhar qualidade dos bots em desenvolvimento e produção |

**Autenticação:** login e senha via Supabase Auth (V1).

**Arquitetura multi-tenant:** planejada para V2+. Na V1 o sistema opera como single-tenant (uma organização). As tabelas já serão projetadas com campo `org_id` nullable para facilitar a migração sem refatoração quando o multi-tenant for ativado.

---

## 4. Stack Tecnológica

| Camada | Tecnologia |
|--------|-----------|
| Framework de avaliação | [DeepEval open source](https://github.com/confident-ai/deepeval) |
| Referência de produto | [Confident AI](https://confident-ai.com) (inspiração de features, não SaaS) |
| Observabilidade / traces | Langfuse (self-hosted, já em uso na VPS) |
| Banco relacional (V1) | Supabase (Postgres gerenciado + Auth) |
| Banco relacional (V2+) | PostgreSQL self-hosted na VPS |
| Banco de dados vetorial | Qdrant (self-hosted, já na VPS) |
| Orquestração de bots | Flowise + LangChain + LangGraph v1 |
| Linguagem | Python |
| Frontend / Dashboard | Next.js + shadcn/ui + Tailwind CSS |
| Backend API (dashboard) | FastAPI (Python) |
| Configuração | `.env` + YAML por ambiente (`config/`) |

> **Nota (pós-M1/M2.1):** esta tabela é a visão de alto nível original do briefing e permanece
> válida em espírito. Detalhes de implementação evoluíram desde então (rename `deepeval/` →
> `deepeval_platform/`; providers de LLM usando classes nativas `deepeval.models.GPTModel/
> AnthropicModel/OpenRouterModel`; Qdrant via `langchain-qdrant` como dependência direta; Langfuse
> SDK `>=4.13.0`) — ver `tech_stack.md` e `.specify/memory/constitution.md` para o estado atual
> e vinculante da stack.

### Regras obrigatórias de desenvolvimento — DeepEval First (principal) e LangChain First (secundário)

> **Atualização (pós-M2.1):** o DeepEval é o **framework principal** deste projeto — o motor
> de avaliação, métricas, Synthesizer, ConversationSimulator e PromptOptimizer são a razão do
> sistema existir. O LangChain/LangGraph é **secundário**: a camada de orquestração dos bots
> *sendo avaliados*, não uma alternativa ao DeepEval. Ver `.specify/memory/constitution.md`
> v1.1.0 (Princípios II e III) para a redação normativa completa.

**DeepEval First (Princípio II — principal):** antes de escrever qualquer código no domínio de
avaliação (métricas, estratégias de avaliação, extração/coleta de traces, geração de datasets
sintéticos, otimização de prompt), verificar se o próprio DeepEval já oferece uma classe,
função ou abstração nativa que atenda à necessidade.
- Se existir → usar como está, sem reimplementar.
- Se não existir → desenvolvimento customizado é permitido (ex.: `TraceExtractor`,
  `EvaluationStrategy` — abstrações de integração específicas deste projeto que adaptam traces
  do Flowise/LangChain ao modelo de test case do DeepEval).

**LangChain First (Princípio III — secundário, escopo restrito):** antes de escrever código de
**orquestração/integração dos bots avaliados**, consultar o MCP do LangChain para verificar se
já existe classe, função ou integração nativa que atenda à necessidade.
> - Se existir → **usar como prioridade**, sem adaptar nem substituir por outro framework
> - Se não existir → aí sim desenvolver do zero
>
> Isso vale para: chains, retrievers, callbacks, loaders, splitters, memory, agents, tools,
> output parsers, e qualquer outro componente usado para conectar/instrumentar os bots avaliados.
> **Não se aplica** aos módulos de domínio de avaliação do próprio sistema (`TraceExtractor`,
> `EvaluationStrategy`, `MetricFactory`, etc.) — esses são regidos pelo DeepEval First acima.

---

## 5. Diretrizes de Desenvolvimento

### 5.1 Arquitetura e Código

**Paradigma obrigatório:** Programação Orientada a Objetos (POO) em todo o projeto, aplicando:
- **Encapsulamento** — dados internos protegidos, interfaces claras
- **Herança** — reaproveitar comportamentos sem duplicar código
- **Polimorfismo** — extensível sem quebrar o que já funciona

**Módulos simples:** cada arquivo tem uma responsabilidade única. Sem arquivos monolíticos. Módulos organizados por domínio (avaliação, coleta, persistência, dashboard).

**Alta coesão, baixo acoplamento** — declarado aqui como exigência técnica não negociável. Cada classe tem missão única; módulos se conhecem o mínimo possível.

### 5.2 Gestão de Configurações — Zero Hardcode

**Nenhuma credencial, chave ou variável sensível no código-fonte.** Sem exceções.

| Tipo de configuração | Onde fica |
|---------------------|-----------|
| Chaves de API, passwords, tokens | `.env` (nunca versionado) |
| Configurações de ambiente (hosts, ports, thresholds) | `config/settings.yaml` |
| Configurações de bots (métricas, schedule) | `config/bots.yaml` |
| Segredos de produção | `.env.production` (nunca versionado) |

Regras:
- `.env`, `.env.*` sempre no `.gitignore`
- Sempre fornecer `.env.example` com chaves sem valores
- Nenhum log, print ou output pode expor segredos
- Leitura de configurações via padrão **Singleton** (uma instância, sem releitura)

### 5.3 Test Driven Development (TDD)

**Testes são escritos ANTES do código de produção.** Fluxo obrigatório:

```
1. Escrever o teste (que vai falhar) ✗
2. Escrever o código mínimo para o teste passar ✓
3. Refatorar mantendo os testes verdes ✓
```

- Framework de testes: `pytest`
- Cobertura mínima esperada: 80%
- Testes unitários por classe/módulo
- Testes de integração para os fluxos principais

### 5.4 Padrões de Projeto (Design Patterns)

| Pattern | Onde aplicar no sistema |
|---------|------------------------|
| **Factory Method** | Criação de métricas DeepEval — `MetricFactory.create("answer_relevancy")` instancia a classe correta sem `if/else` espalhados |
| **Singleton** | `ConfigManager` (leitura do `.env`/YAML), `LangfuseClient`, `QdrantClient` |
| **Strategy** | Estratégias de avaliação por tipo de bot (RAG, agente, conversacional) — troca sem alterar o avaliador principal |
| **Observer** | Notificações de resultado — quando avaliação termina, observadores podem salvar CSV, enviar score ao Langfuse, atualizar dashboard |
| **Repository** | `TraceRepository`, `EvaluationRepository` — isola queries do Langfuse/Qdrant da lógica de negócio |

---

## 6. Versões do Sistema

### Versão 1 — Monitoramento em Produção (Flowise + LangChain/LangGraph)

**Escopo:**
- Integração com Langfuse para buscar traces de bots Flowise e LangChain/LangGraph
- Avaliação automática com **todas** as métricas DeepEval configuráveis por bot
- Envio dos scores de volta ao Langfuse (visível nos traces)
- Exportação de resultados
- Scheduler para rodar avaliações automaticamente
- Dashboard com visão de qualidade por bot ao longo do tempo
- Qdrant para armazenamento de datasets de avaliação e histórico de scores

**Dois modos de integração com Langfuse:**
- **Via Flowise** — integração nativa já configurada; traces chegam automaticamente ao Langfuse quando o bot é acionado via curl. O sistema lê o que já está lá.
- **Direto no código** — bots LangChain/LangGraph usam `langfuse.callback.CallbackHandler` como callback, dando controle total sobre a estrutura do trace. Necessário para garantir que `retrieval_context`, `tools_called` e demais campos cheguem no formato esperado pelo DeepEval.

O `TraceExtractor` usa o padrão **Strategy** para lidar com cada estrutura: `FlowiseExtractor` (adapta o que o Flowise gera) e `LangChainExtractor` (lê a estrutura controlada pelos bots próprios). Novos tipos de bot = nova subclasse de extrator, sem refatoração.

**Objetivo de cobertura:** avaliação **plena e exaustiva** — respostas individuais, RAG, tools/agentes e conversas multi-turno.

#### Tipos de Test Case suportados

| Tipo | Quando usar |
|------|------------|
| `LLMTestCase` | Uma interação única (input → output) |
| `ConversationalTestCase` | Conversa completa (múltiplos turnos) |
| `MLLMTestCase` | Multimodal (texto + imagem) — planejado |

#### Métricas — RAG

| Métrica | O que mede |
|---------|-----------|
| `AnswerRelevancyMetric` | A resposta é relevante para a pergunta? |
| `FaithfulnessMetric` | A resposta está fundamentada no contexto recuperado? |
| `ContextualPrecisionMetric` | O retriever trouxe apenas chunks relevantes? |
| `ContextualRecallMetric` | O retriever cobriu todo o contexto necessário? |
| `ContextualRelevancyMetric` | Os chunks recuperados são relevantes para a pergunta? |
| `HallucinationMetric` | A resposta inventa informações? |

#### Métricas — Agentes e Tools

| Métrica | O que mede |
|---------|-----------|
| `ToolCorrectnessMetric` | O agente chamou as tools certas, na ordem certa? |
| `TaskCompletionMetric` | O agente completou a tarefa proposta? |

#### Métricas — Qualidade e Segurança

| Métrica | O que mede |
|---------|-----------|
| `BiasMetric` | A resposta contém viés? |
| `ToxicityMetric` | A resposta contém conteúdo tóxico? |
| `SummarizationMetric` | O resumo preserva as informações essenciais? |
| `JsonCorrectnessMetric` | O output JSON está no formato esperado? |
| `PromptAlignmentMetric` | A resposta segue as instruções do system prompt? |

#### Métricas — Conversação (multi-turno)

| Métrica | O que mede |
|---------|-----------|
| `ConversationalGEval` | Avaliação customizada de conversas completas |
| `KnowledgeRetentionMetric` | O bot lembrou de informações de turnos anteriores? |
| `RoleAdherenceMetric` | O bot manteve o papel/persona definido? |
| `ConversationCompletenessMetric` | A conversa resolveu o objetivo do usuário? |
| `TurnRelevancyMetric` | As respostas foram relevantes ao longo da conversa? |

#### Métricas — Custom

| Métrica | O que mede |
|---------|-----------|
| `GEval` | Critério customizável via linguagem natural (LLM-as-judge) |
| `DAGMetric` | Avaliação determinística via árvore de decisão |
| `RagasMetric` | Compatibilidade com métricas do Ragas |

---

### Geração de Datasets Sintéticos (V1)

Como não há conversas reais disponíveis no início do projeto, o sistema precisa gerar dados de avaliação sintéticos antes de poder avaliar os bots. O DeepEval oferece duas ferramentas nativas para isso, usadas em conjunto:

#### Por que datasets sintéticos?

- Sem conversas reais, não é possível construir test cases para o DeepEval
- Mesmo quando conversas reais existirem, o dataset sintético funciona como **golden set controlado**: sabemos exatamente qual é a `expected_output`, o que os traces reais não têm
- Diferentes perfis de usuário cobrem ângulos que raramente aparecem todos em um único batch de conversas reais

#### Ferramenta 1 — `Synthesizer` (Golden Set)

Gera goldens (pares input + expected_output) a partir de documentos da empresa. Esses goldens alimentam avaliações de **turno único** (`LLMTestCase`).

```python
from deepeval.synthesizer import Synthesizer
from deepeval.synthesizer.config import StylingConfig

# Gera goldens no "estilo" de um perfil de usuário
styling = StylingConfig(
    scenario="Usuário técnico de TI buscando informações sobre SLA do serviço",
    task="Responder dúvidas sobre contratos e SLAs de telecomunicações empresariais",
    input_format="Perguntas formais e técnicas em português",
    expected_output_format="Resposta objetiva com dados específicos do contrato"
)
synthesizer = Synthesizer(model=llm_provider, styling_config=styling)

# Gera goldens a partir dos documentos da empresa (PDF, DOCX, TXT, MD)
goldens = synthesizer.generate_goldens_from_docs(
    document_paths=["docs/contrato.pdf", "docs/faq_empresas.md"],
    include_expected_output=True
)
# Versão multi-turno:
conv_goldens = synthesizer.generate_conversational_goldens_from_docs(
    document_paths=["docs/contrato.pdf"],
    include_expected_outcome=True
)
```

Pipeline interno do Synthesizer: **Input Generation → Filtration → Evolution → Styling** — produz goldens realistas e variados automaticamente.

#### Ferramenta 2 — `ConversationSimulator` (Conversas Simuladas)

Simula conversas completas entre um **usuário fictício** (persona) e o **bot real**. O simulador chama o bot de verdade a cada turno e registra a resposta. O resultado é um `ConversationalTestCase` pronto para métricas multi-turno.

```python
from deepeval.simulator import ConversationSimulator
from deepeval.dataset import ConversationalGolden
from deepeval.test_case import Turn

# Cada ConversationalGolden = um perfil de usuário em um cenário
golden = ConversationalGolden(
    scenario="Cliente quer entender as opções de upgrade do plano empresarial",
    expected_outcome="Bot explica as opções disponíveis e orienta o cliente para a próxima ação",
    user_description="Gestor financeiro de PME, foco em custo, sem conhecimento técnico de telecom"
)

# model_callback = ponte para o bot real (Flowise via HTTP ou LangChain chain)
async def flowise_callback(input: str) -> Turn:
    response = await flowise_client.send_message(bot_id, input)
    return Turn(role="assistant", content=response)

simulator = ConversationSimulator(
    model_callback=flowise_callback,
    simulator_model=llm_provider
)
conversational_test_cases = simulator.simulate(
    conversational_goldens=[golden],
    max_user_simulations=10
)
```

#### Biblioteca de Personas (`config/personas.yaml`)

Os perfis de usuário ficam em um arquivo de configuração versionado. O `SyntheticDatasetGenerator` lê as personas e gera um conjunto de goldens e conversas para **cada perfil**, maximizando a cobertura de cenários.

```yaml
# config/personas.yaml
personas:
  - id: gestor_ti
    name: "Gestor de TI"
    description: "Technical IT manager, formal language, asks about integrations, SLAs and technical specs"
    communication_style: "formal, technical, objective"
    typical_scenarios:
      - "Consulta sobre SLA do contrato"
      - "Abertura de chamado técnico"
      - "Verificação de status de serviço"

  - id: usuario_basico
    name: "Usuário Básico"
    description: "Regular employee, non-technical, simple Portuguese, often confused about terminology"
    communication_style: "informal, simple, sometimes frustrated"
    typical_scenarios:
      - "Problemas de acesso a sistemas"
      - "Dúvidas sobre cobrança"
      - "Solicitar suporte básico"

  - id: cliente_insatisfeito
    name: "Cliente Insatisfeito"
    description: "Customer with a recurring problem, already contacted support before, impatient tone"
    communication_style: "direct, slightly aggressive, wants quick resolution"
    typical_scenarios:
      - "Reclamação de serviço intermitente"
      - "Cobrança incorreta recorrente"
      - "Escalada de atendimento"

  - id: cliente_novo
    name: "Cliente Novo"
    description: "New business customer, exploring options, asks many questions, polite tone"
    communication_style: "curious, polite, many follow-up questions"
    typical_scenarios:
      - "Entender opções de planos"
      - "Comparar serviços disponíveis"
      - "Processo de contratação"
```

#### Módulo `SyntheticDatasetGenerator`

| Responsabilidade | Detalhes |
|----------------|---------|
| Ler personas | Carrega `config/personas.yaml` via `ConfigManager` |
| Gerar goldens por persona | Usa `Synthesizer` com `StylingConfig` moldado a cada perfil |
| Simular conversas por persona | Usa `ConversationSimulator` com `ConversationalGolden` por persona × cenário |
| Persistir datasets | Salva no Supabase (metadados) + Qdrant (embeddings para busca semântica) + JSON/CSV local |
| Alimentar o avaliador | Datasets prontos para uso pelo `Evaluator` principal |

**Fluxo:**

```
config/personas.yaml
config/knowledge_base/ (PDFs, MDs, DOCXs da empresa)
        ↓
SyntheticDatasetGenerator
    ├── Synthesizer → [Golden] → LLMTestCase (avaliação single-turn)
    └── ConversationSimulator → [ConversationalTestCase] (avaliação multi-turno)
        ↓
EvaluationDataset (DeepEval)
        ↓
Evaluator (métricas DeepEval)
```

**Configuração no `.env`:**
```bash
SYNTHETIC_DOCS_DIR=./config/knowledge_base   # pasta com documentos da empresa
SYNTHETIC_OUTPUT_DIR=./datasets              # onde salvar os datasets gerados
SYNTHETIC_GOLDENS_PER_PERSONA=20             # quantos goldens por persona (single-turn)
SYNTHETIC_CONVERSATIONS_PER_PERSONA=5        # quantas conversas por persona (multi-turn)
```

---

### Otimização de Prompts (V1 — modo manual / V2 — modo automático)

Após a avaliação gerar scores, o sistema oferece um módulo de **otimização de prompts** que fecha o ciclo de melhoria contínua: em vez de o desenvolvedor ajustar o prompt na intuição, o DeepEval testa variações e sugere a versão otimizada com base nas métricas.

#### Como funciona o `PromptOptimizer`

O DeepEval oferece dois algoritmos de otimização, ambos baseados em pesquisa científica:

| Algoritmo | Abordagem | Quando usar |
|-----------|-----------|-------------|
| **GEPA** (padrão) | Busca genética com fronteira de Pareto — mantém as melhores variações e evolui a partir delas | Múltiplas métricas simultâneas |
| **MIPROv2** | Busca bayesiana com seleção epsilon-greedy | Otimização de métrica única com menos custo |

O otimizador recebe o prompt atual, o dataset de goldens e as métricas, testa N variações do prompt chamando o bot, compara os scores e retorna o melhor candidato com relatório completo da evolução.

#### Modo V1 — Manual (lançamento)

No início, o fluxo é semi-automático: o sistema gera a sugestão de prompt otimizado, o desenvolvedor analisa, aplica manualmente no bot (Flowise ou LangChain) e roda uma nova avaliação para confirmar a melhora.

```
Avaliação → scores baixos em alguma métrica
      ↓
PromptOptimizer.optimize(prompt_atual, goldens, métricas)
      ↓
Sugestão de prompt otimizado exibida no dashboard
      ↓
Desenvolvedor analisa e aplica manualmente no bot
      ↓
Nova avaliação → comparação de scores (antes vs. depois)
      ↓
Nova versão do prompt salva no Langfuse (versionamento nativo)
```

#### Modo V2 — Automático (LangChain/LangGraph)

Para bots LangChain/LangGraph, onde o sistema tem controle direto sobre o prompt, a aplicação pode ser automatizada: o otimizador injeta o novo prompt candidato no bot durante os testes, sem intervenção manual.

#### Flowise — Investigação pendente

Para bots Flowise, é necessário investigar se a API permite sobrescrever o system prompt no momento da chamada (via parâmetro no request). Se possível, automatizar; caso contrário, manter o fluxo manual. **Não bloqueia o V1.**

#### Versionamento de prompts via Langfuse

O Langfuse tem versionamento de prompts nativo. Cada versão otimizada fica registrada com timestamp, scores antes/depois e o diff do prompt — visível diretamente nos traces.

---

### Versão 2 — CI/CD + Avaliação Pré-Deploy

**Escopo (planejado):**
- Dataset de testes fixos para avaliação antes de cada deploy
- Comparação entre versões do mesmo bot (A/B de qualidade)
- Alertas automáticos (Slack/e-mail) quando qualidade cair abaixo do threshold

---

## 7. Critérios de Sucesso

- [ ] Qualquer bot configurado em `bots.yaml` é avaliado sem código adicional
- [ ] Todas as métricas DeepEval podem ser ativadas por bot via configuração
- [ ] Avaliação cobre respostas individuais, RAG, tools/agentes e conversas multi-turno
- [ ] Datasets sintéticos gerados a partir dos documentos da empresa e personas configuradas
- [ ] Cada persona em `personas.yaml` gera goldens (single-turn) e conversas simuladas (multi-turn)
- [ ] Sistema sugere prompt otimizado após avaliação com scores abaixo do threshold
- [ ] Histórico de versões de prompt disponível no Langfuse com scores antes/depois
- [ ] Zero hardcode — nenhuma credencial no código-fonte
- [ ] Scores aparecem no Langfuse vinculados a cada trace
- [ ] Dashboard mostra evolução da qualidade por bot, por métrica e por período
- [ ] Equipe técnica acessa sem depender de Marcio
- [ ] Cobertura de testes ≥ 80% via TDD
- [ ] Sistema suporta novos bots, métricas e personas sem refatoração

---

## 8. Fora do Escopo (v1)

- Multi-tenant (múltiplas organizações) — v2
- Interface para usuários finais (não-técnicos)
- Avaliação de bots de terceiros
- Alertas automáticos — v2
- Pipeline CI/CD pré-deploy — v2
- Migração para Postgres self-hosted — v2

---

## 9. Próximos Passos

> **Nota (pós-M1):** o item "Definir stack do dashboard" foi removido desta lista — a stack já está definida desde a v1.0 deste documento (seção 4: Next.js + shadcn/ui + Tailwind CSS + FastAPI) e detalhada em `tech_stack.md` §2.15. Não é uma decisão pendente.

1. **Aprovar este briefing**
2. **Gerar Feature Specs** por módulo:
   - Módulo de configuração (`ConfigManager` — Singleton)
   - Módulo de coleta de traces (Langfuse + Repository)
   - Módulo de extração de traces (`FlowiseExtractor` + `LangChainExtractor` — Strategy)
   - Módulo de providers de LLM (`LLMProviderFactory` — Factory + Strategy)
   - Módulo de métricas (`MetricFactory` — Factory Method)
   - Módulo de avaliação (`Evaluator` — orquestra tudo)
   - Módulo de datasets sintéticos (`SyntheticDatasetGenerator` — Synthesizer + ConversationSimulator)
   - Módulo de otimização de prompts (`PromptOptimizationModule` — PromptOptimizer GEPA/MIPROv2)
   - Módulo de persistência (Qdrant + Supabase + Repository)
   - Módulo de notificação/export (`ResultPublisher` — Observer)
   - Módulo de dashboard
   - Módulo de scheduler (APScheduler)
3. **Decidir o que aproveitar** do protótipo `deepeval-leadmedia/`
4. **Iniciar desenvolvimento com TDD**

---

## 10. Referências

- DeepEval open source: https://github.com/confident-ai/deepeval
- DeepEval docs: https://deepeval.com/docs/getting-started
- Confident AI (referência de produto): https://confident-ai.com
- Langfuse: self-hosted na VPS
- Qdrant: self-hosted na VPS
- Protótipo existente: `deepeval-leadmedia/`
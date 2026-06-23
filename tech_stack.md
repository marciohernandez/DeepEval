# Tech Stack – Sistema de Avaliação de Chatbots

**Projeto:** DeepEval Chatbot Evaluator  
**Data:** 2026-06-19  
**Versão do documento:** 1.0  

---

## 1. Visão Geral

```
┌──────────────────────────────────────────────────────────┐
│                    DASHBOARD (Frontend)                  │
│         Next.js · shadcn/ui · Tailwind · Recharts        │
│                  Inspiração: Confident AI                │
├──────────────────────────────────────────────────────────┤
│                   BACKEND API (FastAPI)                  │
│              REST API · Supabase Auth JWT                │
├──────────────────────────────────────────────────────────┤
│                    CICLO DE QUALIDADE                    │
│  Datasets Sintéticos → Avaliação → Otimização de Prompt  │
│   (Synthesizer +      (DeepEval 4.x)   (PromptOptimizer) │
│  ConversationSimulator)                 GEPA / MIPROv2   │
├──────────────┬───────────────────────────────────────────┤
│   COLETA     │          ORQUESTRAÇÃO DE BOTS             │
│  Langfuse    │  LangChain 1.3.x + LangGraph 1.2.x        │
│   4.9.x      │  + Flowise (self-hosted)                  │
├──────────────┴───────────────────────────────────────────┤
│                      PERSISTÊNCIA                        │
│   Supabase (relacional) · Qdrant (vetorial) · CSV        │
├──────────────────────────────────────────────────────────┤
│                    INFRAESTRUTURA                        │
│      Python 3.11+ · Docker · APScheduler                 │
│      python-dotenv · PyYAML · pytest                     │
└──────────────────────────────────────────────────────────┘
```

---

## 2. Stack por Camada

### 2.1 Linguagem e Runtime

| Tecnologia | Versão | Justificativa |
|-----------|--------|---------------|
| **Python** | `^3.11` | Suportado por todas as libs do projeto; tipagem moderna com `match/case` e `TypeAlias` |

---

### 2.2 Framework de Avaliação (core)

| Tecnologia | Versão | Papel | Fonte |
|-----------|--------|-------|-------|
| **DeepEval** | `^4.0.6` | Todas as métricas de avaliação de LLMs | [GitHub](https://github.com/confident-ai/deepeval) |

**Referência de produto:** [Confident AI](https://confident-ai.com) — usado como inspiração de features e UX, não como SaaS. O sistema roda 100% open source e self-hosted.

**Métricas ativas:** AnswerRelevancy, Faithfulness, ContextualPrecision, ContextualRecall, ContextualRelevancy, Hallucination, ToolCorrectness, TaskCompletion, Bias, Toxicity, Summarization, JsonCorrectness, PromptAlignment, KnowledgeRetention, RoleAdherence, ConversationCompleteness, ConversationRelevancy, GEval, DAGMetric, RagasMetric.

---

### 2.3 Observabilidade e Traces

| Tecnologia | Versão | Papel |
|-----------|--------|-------|
| **Langfuse Python SDK** | `^4.9.1` | Buscar traces dos chatbots; enviar scores de avaliação de volta |
| **Langfuse** (servidor) | self-hosted na VPS | Armazena todos os traces dos bots em produção |

**Dois modos de integração suportados:**

| Modo | Quando usar | Como funciona |
|------|------------|---------------|
| **Via Flowise** | Bots criados no Flowise | Flowise envia traces ao Langfuse automaticamente pela integração nativa. O sistema apenas lê. |
| **Direto no código** | Bots LangChain/LangGraph | O bot usa `langfuse.callback.CallbackHandler` como callback do LangChain. Dá controle total sobre a estrutura do trace. |

```python
# Modo 2 — integração direta em bots LangChain/LangGraph
from langfuse.callback import CallbackHandler

handler = CallbackHandler()  # lê LANGFUSE_* do .env automaticamente
result = chain.invoke(input, config={"callbacks": [handler]})
```

**Por que os dois modos?**
- Flowise não expõe controle sobre a estrutura do trace — o sistema precisa inspecionar e adaptar
- LangChain/LangGraph com integração direta gera traces com estrutura previsível e controlada
- O `TraceExtractor` usa Strategy para lidar com cada estrutura: `FlowiseExtractor` e `LangChainExtractor`

**Fluxo de dados:**
- **Entrada:** `langfuse.api.observations.get_many()` — busca traces por período/tag/session
- **Saída:** `langfuse.score()` — publica scores vinculados a cada trace

---

### 2.4 Orquestração de Bots Avaliados

| Tecnologia | Versão | Papel |
|-----------|--------|-------|
| **LangChain** | `^1.3.10` | Bots LangChain + integrações nativas (retrievers, callbacks, tools) |
| **LangGraph** | `^1.2.6` | Bots com fluxo de agentes multi-step |
| **Flowise** | self-hosted | Bots low-code já em produção (V1) |

> **Regra:** Antes de qualquer código, consultar o MCP do LangChain. Se existir classe/função nativa → usar. Só desenvolver do zero se não existir.

---

### 2.5 Banco de Dados Relacional (persistência principal)

| Tecnologia | Versão/Plano | Papel |
|-----------|--------|-------|
| **Supabase** | V1 (cloud/self-hosted) | Postgres gerenciado com auth, storage e REST API prontos |
| **PostgreSQL** | V2+ (self-hosted na VPS) | Migração para Postgres puro quando o sistema amadurecer |

**Supabase na V1 entrega de graça:**
- Postgres com interface visual
- Autenticação (login/senha) via `supabase-py`
- Row Level Security (RLS) — fundação para multi-tenant futuro
- API REST automática sobre as tabelas

**Tabelas principais (V1):**
- `users` — login/senha via Supabase Auth
- `bots` — configuração dos bots avaliados
- `evaluation_runs` — cada execução do avaliador
- `evaluation_results` — scores por trace/métrica

**Estratégia de migração V1 → V2:**
- Toda persistência via `Repository` (pattern) — troca Supabase por Postgres puro sem tocar em regras de negócio
- `.env` define qual backend usar: `DB_PROVIDER=supabase` ou `DB_PROVIDER=postgres`

---

### 2.6 Multi-Tenant (arquitetura planejada)

> **V1: sistema single-tenant** — um único time/organização usa o sistema.  
> **V2+: multi-tenant** — cada cliente/organização vê apenas seus próprios bots e resultados.

**Como o Supabase prepara o V2:**
- Row Level Security (RLS) já existe no Postgres/Supabase — basta adicionar coluna `org_id` e políticas RLS
- Supabase Auth suporta organizações e papéis nativamente
- A separação de dados por tenant é feita no banco, não na aplicação

**O que NÃO fazer na V1 para não bloquear o V2:**
- Nunca usar `user_id` hardcoded como escopo global
- Projetar tabelas já com campo `org_id` nullable (preenchido quando o multi-tenant for ativado)

---

### 2.7 Banco de Dados Vetorial

| Tecnologia | Versão | Papel |
|-----------|--------|-------|
| **Qdrant** | `^1.18.0` (client) | Armazenar datasets de avaliação e embeddings para busca semântica |
| **Qdrant** (servidor) | self-hosted na VPS | Já disponível na infraestrutura atual |

**Uso no sistema:**
- Datasets de golden-set para avaliações (conjuntos de perguntas + respostas esperadas)
- Busca semântica de traces similares para análise de padrões

---

### 2.8 Provedores de LLM (LLM Providers)

O sistema adota uma **arquitetura de providers extensível**: qualquer ponto que precise de um LLM (modelo juiz, embeddings, análise) passa por uma abstração que permite trocar ou combinar provedores sem mudar o código que os usa.

#### Provedores suportados

| Provider | SDK | Modelos exemplo | Papel no sistema |
|---------|-----|----------------|-----------------|
| **OpenAI** | `openai>=1.30.0` | `gpt-4o`, `gpt-4o-mini` | Modelo juiz padrão para métricas DeepEval |
| **Anthropic** | `anthropic>=0.30.0` | `claude-opus-4-8`, `claude-sonnet-4-6`, `claude-haiku-4-5` | Alternativa de alta precisão |
| **OpenRouter** | `openai>=1.30.0` (base URL alternativa) | Qualquer modelo do catálogo | Acesso unificado a centenas de modelos via uma API key |

> **OpenRouter** usa o mesmo SDK da OpenAI — só muda a `base_url` para `https://openrouter.ai/api/v1`. Nenhuma dependência extra.

#### Arquitetura de abstração

```
LLMProviderBase (DeepEvalBaseLLM)
    ├── OpenAIProvider
    ├── AnthropicProvider
    ├── OpenRouterProvider
    └── [FuturoProvider]  ← adicionar novo provider = criar nova subclasse
```

- `LLMProviderBase` implementa `DeepEvalBaseLLM` — integração nativa com todas as métricas DeepEval
- `LLMProviderFactory.create(provider, model)` — instancia o provider correto a partir do `.env`
- Adicionar novo provider = criar uma subclasse + registrar na Factory, **sem tocar no restante do sistema**

#### Configuração no `.env`

```bash
# Provider padrão do sistema
LLM_PROVIDER=openrouter        # openai | anthropic | openrouter

# Modelo padrão por provider
OPENAI_DEFAULT_MODEL=gpt-4o-mini
ANTHROPIC_DEFAULT_MODEL=claude-haiku-4-5-20251001
OPENROUTER_DEFAULT_MODEL=anthropic/claude-3.5-haiku

# Chaves de API (preencher apenas os providers que usar)
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
OPENROUTER_API_KEY=sk-or-...
```

#### Seleção de provider por contexto

Cada bot em `bots.yaml` poderá especificar o provider e modelo a usar para avaliação:

```yaml
bots:
  - name: "bot-principal"
    eval_provider: openrouter          # sobrescreve o padrão do .env
    eval_model: google/gemini-flash-1.5
    metrics:
      - answer_relevancy
      - faithfulness
```

Se não especificado, usa o `LLM_PROVIDER` + modelo padrão do `.env`.

---

### 2.9 Otimização de Prompts

O DeepEval oferece `PromptOptimizer` para fechar o ciclo de melhoria: avalia o prompt atual, testa variações e retorna o candidato com melhor score nas métricas definidas.

| Tecnologia | Papel |
|-----------|-------|
| **`PromptOptimizer`** (DeepEval) | Otimiza o system prompt do bot com base nos resultados de avaliação |
| **GEPA** (algoritmo padrão) | Busca genética com fronteira de Pareto — recomendado para múltiplas métricas |
| **MIPROv2** | Busca bayesiana — recomendado para otimização com menor custo de tokens |
| **Langfuse Prompt Versioning** | Armazena cada versão do prompt com scores antes/depois |

**Modo V1 — Manual:**
```python
from deepeval.optimizer import PromptOptimizer
from deepeval.prompt import Prompt

optimizer = PromptOptimizer(
    metrics=[AnswerRelevancyMetric(), FaithfulnessMetric()],
    model_callback=bot_callback  # chama o bot com o prompt candidato
)
result = optimizer.optimize(
    prompt=Prompt(text_template=current_system_prompt),
    goldens=evaluation_dataset.goldens
)
# result.text_template → novo prompt sugerido (aplicado manualmente no bot)
# optimizer.optimization_report → histórico completo das variações testadas
```

**Configuração no `.env`:**
```bash
PROMPT_OPTIMIZER_ALGORITHM=gepa        # gepa | miprov2
PROMPT_OPTIMIZER_MAX_CONCURRENT=10     # paralelismo durante otimização
```

**Pendência investigar (Flowise):** verificar se a API do Flowise aceita `overrideConfig.systemPrompt` no body do request — se sim, o modo automático pode ser ativado para bots Flowise sem mudança de arquitetura.

---

### 2.10 Geração de Datasets Sintéticos

O DeepEval fornece duas classes nativas para geração de dados sintéticos — usadas pelo módulo `SyntheticDatasetGenerator`.

| Classe | Papel |
|--------|-------|
| **`Synthesizer`** | Gera goldens (input + expected_output) a partir de documentos da empresa → alimenta `LLMTestCase` |
| **`ConversationSimulator`** | Simula conversas completas chamando o bot real → gera `ConversationalTestCase` |

**`Synthesizer`** — configurável via:
- `StylingConfig(scenario, task, input_format, expected_output_format)` — molda os goldens ao estilo de cada persona
- `EvolutionConfig` — controla complexidade (raciocínio, multi-contexto, restrições)
- `FiltrationConfig` — garante qualidade mínima dos inputs gerados

**`ConversationSimulator`** — campos-chave do `ConversationalGolden`:
- `scenario` — o que o usuário quer fazer nessa conversa
- `expected_outcome` — como deve terminar uma conversa bem-sucedida
- `user_description` — **o perfil/persona do usuário** (é aqui que as personas entram)

**Personas** — definidas em `config/personas.yaml` (versionado, não sensível):
- Cada persona → `StylingConfig` no Synthesizer + `ConversationalGolden.user_description` no Simulator
- Exemplos: Gestor de TI, Usuário Básico, Cliente Insatisfeito, Cliente Novo

**`model_callback`** no `ConversationSimulator` — adaptado por tipo de bot:
- Flowise → HTTP call ao endpoint do bot
- LangChain/LangGraph → invoca a chain/graph diretamente

---

### 2.10 Agendamento

| Tecnologia | Versão | Papel |
|-----------|--------|-------|
| **APScheduler** | `^3.10.0` | Scheduler de avaliações por bot com cron expressions |

---

### 2.11 Configuração e Segurança

| Tecnologia | Versão | Papel |
|-----------|--------|-------|
| **python-dotenv** | `^1.0.0` | Leitura do `.env` — ÚNICA fonte de variáveis sensíveis |
| **PyYAML** | `^6.0` | Leitura de `config/bots.yaml` e `config/settings.yaml` |

**Regras absolutas:**
- Nenhuma credencial no código-fonte
- `.env` e `.env.*` sempre no `.gitignore`
- `.env.example` sempre presente com chaves sem valores
- `ConfigManager` (Singleton) é o único ponto de leitura de config no sistema
- Logs nunca expõem valores de variáveis sensíveis

---

### 2.12 Testes

| Tecnologia | Versão | Papel |
|-----------|--------|-------|
| **pytest** | `^8.0.0` | Framework principal de testes (TDD) |
| **pytest-cov** | `^5.0.0` | Cobertura de código (meta: ≥ 80%) |
| **pytest-asyncio** | `^0.23.0` | Testes de métodos assíncronos |
| **pytest-mock** | `^3.14.0` | Mocks para isolamento de unidades |

**Fluxo TDD obrigatório:**
```
1. Escrever o teste → RED (falha)
2. Escrever código mínimo → GREEN (passa)
3. Refatorar → GREEN mantido
```

---

### 2.13 Containerização

| Tecnologia | Papel |
|-----------|-------|
| **Docker** | Container da aplicação |
| **Docker Compose** | Orquestração local (app + Langfuse + Qdrant) |
| **Dockerfile** | Imagem Python com dependências fixadas |

---

### 2.14 Frontend / Dashboard

**Inspiração de produto:** [Confident AI](https://www.confident-ai.com) — tema escuro, tabelas de resultados com badges PASS/FAIL, gráficos de evolução de qualidade, visualização de trace tree, histórico de versões de prompt.

#### Stack definida

| Camada | Tecnologia | Papel |
|--------|-----------|-------|
| **Backend API** | FastAPI (`^0.115.0`) | API REST Python que expõe os dados de avaliação ao frontend |
| **Frontend** | Next.js (`^14.0`) | Framework React com App Router, SSR e rotas de API |
| **Componentes UI** | shadcn/ui | Biblioteca de componentes com tema escuro profissional out-of-the-box |
| **Estilização** | Tailwind CSS (`^3.4`) | Utilitários CSS — integrado ao shadcn/ui |
| **Gráficos** | Recharts | Gráficos de linha/barra para evolução de scores e comparação entre runs |
| **Tabelas** | TanStack Table (`^8`) | Tabelas com filtros, ordenação e paginação para resultados de avaliação |

#### Arquitetura do dashboard

```
┌──────────────────────────────────────────┐
│           FRONTEND (Next.js)             │
│  shadcn/ui · Tailwind · Recharts         │
│  TanStack Table · Dark theme             │
└────────────────┬─────────────────────────┘
                 │ HTTP / REST
┌────────────────▼─────────────────────────┐
│           BACKEND API (FastAPI)          │
│  Expõe dados do Supabase + Qdrant        │
│  Autenticação via Supabase Auth JWT      │
└────────────────┬─────────────────────────┘
                 │
┌────────────────▼─────────────────────────┐
│           PERSISTÊNCIA                   │
│  Supabase (resultados) · Qdrant (vetores)│
└──────────────────────────────────────────┘
```

#### Telas principais (inspiração Confident AI)

| Tela | Conteúdo |
|------|---------|
| **Overview** | Cards com score médio por bot, alertas de qualidade, última avaliação |
| **Bot Detail** | Evolução de scores por métrica ao longo do tempo (linha chart) |
| **Evaluation Run** | Tabela de test cases com input, output, score por métrica, PASS/FAIL |
| **Datasets** | Gerenciamento de goldens e personas por bot |
| **Prompt History** | Versões de prompt com scores antes/depois, sugestão do PromptOptimizer |
| **Settings** | Configuração de bots, métricas ativas, personas, thresholds |

#### Dependências adicionais (requirements.txt)

```text
# Backend API
fastapi>=0.115.0,<1.0.0
uvicorn>=0.30.0,<1.0.0
python-jose>=3.3.0        # JWT decode para auth Supabase
```

#### Dependências frontend (package.json)

```json
{
  "dependencies": {
    "next": "^14.0.0",
    "react": "^18.0.0",
    "tailwindcss": "^3.4.0",
    "recharts": "^2.12.0",
    "@tanstack/react-table": "^8.0.0"
  }
}
```

> shadcn/ui é instalado via CLI (`npx shadcn@latest init`) — não é uma dependência npm direta, mas um gerador de componentes que copia código para o projeto.

---

## 3. Padrões de Projeto Adotados

| Pattern | Onde aplicar |
|---------|-------------|
| **Singleton** | `ConfigManager`, `LangfuseClient`, `QdrantClient` |
| **Factory Method** | `MetricFactory.create(name)` — instancia métricas DeepEval sem `if/else`; `LLMProviderFactory.create(provider, model)` — instancia o provider correto |
| **Strategy** | `TraceExtractor` — estratégia por tipo de bot (Flowise vs LangChain vs LangGraph) |
| **Observer** | `ResultPublisher` — notifica Langfuse, CSV, Qdrant após avaliação |
| **Repository** | `TraceRepository`, `EvaluationRepository` — isola queries da lógica de negócio |

---

## 4. requirements.txt (base)

```text
# Avaliação
deepeval>=4.0.6,<5.0.0

# Observabilidade
langfuse>=4.9.1,<5.0.0

# Orquestração
langchain>=1.3.10,<2.0.0
langgraph>=1.2.6,<2.0.0

# Banco relacional (V1 — Supabase)
supabase>=2.0.0,<3.0.0

# Banco vetorial
qdrant-client>=1.18.0,<2.0.0

# LLM Providers
openai>=1.30.0,<2.0.0        # OpenAI + OpenRouter (mesma lib, base_url diferente)
anthropic>=0.30.0,<1.0.0     # Anthropic

# Agendamento
APScheduler>=3.10.0,<4.0.0

# Configuração
python-dotenv>=1.0.0
PyYAML>=6.0

# Testes
pytest>=8.0.0
pytest-cov>=5.0.0
pytest-asyncio>=0.23.0
pytest-mock>=3.14.0
```

---

## 5. Estrutura de Configuração

```
config/
├── bots.yaml               # Configuração dos bots e métricas (não sensível, versionado)
├── settings.yaml           # Configurações gerais de ambiente (não sensível, versionado)
├── personas.yaml           # Perfis de usuário para datasets sintéticos (versionado)
└── knowledge_base/         # Documentos da empresa para geração de goldens (versionado)
    ├── faq_empresas.md
    ├── contrato_servicos.pdf
    └── ...

.env                        # Chaves e segredos (NUNCA versionado)
.env.example                # Template com chaves sem valores (versionado)
.gitignore                  # Inclui .env, .env.*, venv/, __pycache__/
datasets/                   # Datasets gerados (gitignore ou LFS)
```

**Variáveis obrigatórias no `.env`:**
```bash
# Langfuse
LANGFUSE_HOST=http://seu-host:3000
LANGFUSE_PUBLIC_KEY=pk-...
LANGFUSE_SECRET_KEY=sk-...

# LLM Judge
OPENAI_API_KEY=sk-...
EVAL_MODEL=gpt-4o-mini        # ou gpt-4o

# Banco relacional (Supabase V1)
DB_PROVIDER=supabase           # supabase | postgres
SUPABASE_URL=https://xxxx.supabase.co
SUPABASE_SERVICE_KEY=service_role_key...
SUPABASE_ANON_KEY=anon_key...

# (Para V2+ com Postgres puro)
# DB_PROVIDER=postgres
# DATABASE_URL=postgresql://user:pass@host:5432/dbname

# Qdrant
QDRANT_HOST=http://seu-host
QDRANT_PORT=6333
QDRANT_API_KEY=               # se usar autenticação

# Otimização de Prompts
PROMPT_OPTIMIZER_ALGORITHM=gepa         # gepa | miprov2
PROMPT_OPTIMIZER_MAX_CONCURRENT=10

# Datasets Sintéticos
SYNTHETIC_DOCS_DIR=./config/knowledge_base    # documentos da empresa (PDFs, MDs, DOCXs)
SYNTHETIC_OUTPUT_DIR=./datasets               # onde salvar os datasets gerados
SYNTHETIC_GOLDENS_PER_PERSONA=20              # goldens por persona (single-turn)
SYNTHETIC_CONVERSATIONS_PER_PERSONA=5         # conversas simuladas por persona (multi-turn)

# Sistema
SCORE_THRESHOLD=0.7
OUTPUT_DIR=./resultados
DRY_RUN=false
```

---

## 6. Decisões em Aberto

| Decisão | Status | Impacto |
|---------|--------|---------|
| **Frontend / Dashboard** | **Definido:** Next.js + shadcn/ui + Tailwind + FastAPI | Stack completa documentada na seção 2.14 |
| Modelo juiz padrão (gpt-4o-mini vs Ollama local) | Flexível via `.env` | Custo vs precisão |
| Supabase cloud vs self-hosted | **Definido: cloud** (supabase.com) | URL e keys vêm do painel do Supabase |
| Autenticação no Qdrant | **Definido: tem API key** | Variável `QDRANT_API_KEY` obrigatória no `.env` |

---

## 7. Referências

- DeepEval open source: https://github.com/confident-ai/deepeval
- DeepEval docs: https://deepeval.com/docs/getting-started
- Langfuse SDK: https://langfuse.com/docs/query-traces
- LangChain: https://python.langchain.com
- LangGraph: https://langchain-ai.github.io/langgraph
- Qdrant: https://qdrant.tech/documentation

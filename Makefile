# =============================================================================
# DeepEval Chatbot Evaluator — Makefile
# =============================================================================
#
# Interface única para todos os comandos de desenvolvimento.
# Uso: make <target>
#
# Requisitos:
#   - uv        (gerenciador de dependências Python)
#   - make      (GNU Make)
#   - docker    (para targets de infra, opcional)
#
# Convenção de diretórios de teste:
#   tests/unit/         Testes unitários por classe/módulo
#   tests/integration/  Testes de integração dos fluxos principais
#   tests/contract/     Testes de contrato entre módulos e APIs externas
#   tests/e2e/          Testes end-to-end (avaliação completa de ponta a ponta)
# =============================================================================

# -----------------------------------------------------------------------------
# Variáveis
# -----------------------------------------------------------------------------

PYTHON       := uv run python
PYTEST       := uv run pytest
RUFF         := uv run ruff

# Diretórios
SRC_DIR      := src
TEST_DIR     := tests
UNIT_DIR     := $(TEST_DIR)/unit
INTEG_DIR    := $(TEST_DIR)/integration
CONTRACT_DIR := $(TEST_DIR)/contract
E2E_DIR      := $(TEST_DIR)/e2e
DATASET_DIR  := datasets
RESULTS_DIR  := resultados

# Cobertura mínima exigida pela constituição (Princípio III — TDD)
MIN_COVERAGE := 80

# Flags padrão do pytest
PYTEST_FLAGS := -v --tb=short

# Flags de cobertura
COV_FLAGS    := --cov=$(SRC_DIR) --cov-report=term-missing --cov-report=html:htmlcov \
                --cov-fail-under=$(MIN_COVERAGE)

# Flags para testes assíncronos (pytest-asyncio)
ASYNC_FLAGS  := --asyncio-mode=auto

.DEFAULT_GOAL := help

# Torna todos os targets .PHONY (não geram arquivos com o mesmo nome)
.PHONY: help \
        sync install \
        run \
        test test-unit test-integration test-contract test-e2e test-async \
        test-config test-collection test-extraction test-providers \
        test-metrics test-evaluation test-dataset test-optimization \
        test-persistence test-publisher test-scheduler test-dashboard \
        cov cov-unit cov-integration cov-html \
        generate evaluate optimize \
        lint format check \
        docker-up docker-down docker-logs docker-build \
        clean clean-cache clean-datasets clean-results clean-all


# =============================================================================
# HELP
# =============================================================================

help: ## Exibe este menu de ajuda com todos os targets disponíveis
	@echo ""
	@echo "  DeepEval Chatbot Evaluator — Makefile"
	@echo "  ======================================"
	@echo ""
	@awk 'BEGIN {FS = ":.*##"} \
		/^##[[:space:]]/ { \
			gsub(/^## ?/, "", $$0); \
			printf "\n  \033[1;34m%s\033[0m\n", $$0 \
		} \
		/^[a-zA-Z_-]+:.*##/ { \
			printf "  \033[36m%-28s\033[0m %s\n", $$1, $$2 \
		}' $(MAKEFILE_LIST)
	@echo ""


# =============================================================================
# SETUP E DEPENDÊNCIAS
# =============================================================================

## Setup & Dependências

sync: ## Instala/atualiza todas as dependências via uv
	uv sync

install: sync ## Alias para sync (compatibilidade com convenção comum)


# =============================================================================
# EXECUÇÃO
# =============================================================================

## Execução

run: ## Executa a aplicação principal (main.py)
	$(PYTHON) main.py

run-api: ## Inicia o backend FastAPI (dashboard)
	$(PYTHON) -m uvicorn src.dashboard.api:app --reload --host 0.0.0.0 --port 8000

run-scheduler: ## Inicia o scheduler de avaliações automáticas (APScheduler)
	$(PYTHON) -m src.scheduler.runner


# =============================================================================
# TESTES — VISÃO GERAL
# =============================================================================
#
# Hierarquia de testes (da base ao topo):
#
#   unit        → Testa uma única classe/função isolada, sem I/O real
#   integration → Testa o fluxo entre módulos internos (ex: Evaluator + MetricFactory)
#   contract    → Testa o contrato com serviços externos (Langfuse, Supabase, Qdrant)
#   e2e         → Testa o ciclo completo: coleta → avaliação → persistência → publicação
#   async       → Filtro transversal: roda apenas testes assíncronos (qualquer camada)
#
# Fluxo TDD obrigatório (Princípio III da Constituição):
#   1. make test-unit       → RED  (teste falha antes da implementação)
#   2. [implementar código]
#   3. make test-unit       → GREEN (teste passa)
#   4. make cov             → verificar cobertura ≥ 80%
#
# =============================================================================

## Testes — Suite Completa

test: ## Roda TODOS os testes (unit + integration + contract + e2e)
	$(PYTEST) $(PYTEST_FLAGS) $(ASYNC_FLAGS) $(TEST_DIR)/

test-fast: ## Roda apenas testes rápidos (exclui e2e e contract, que dependem de serviços)
	$(PYTEST) $(PYTEST_FLAGS) $(ASYNC_FLAGS) \
		--ignore=$(E2E_DIR) \
		--ignore=$(CONTRACT_DIR) \
		$(TEST_DIR)/

test-ci: ## Suite para CI/CD: todos os testes + cobertura mínima obrigatória
	$(PYTEST) $(PYTEST_FLAGS) $(ASYNC_FLAGS) $(COV_FLAGS) $(TEST_DIR)/


# =============================================================================
# TESTES — POR CAMADA
# =============================================================================

## Testes — Por Camada

test-unit: ## Roda apenas testes unitários (tests/unit/)
	@echo "→ Testes unitários: isolados por classe/módulo, sem I/O externo"
	$(PYTEST) $(PYTEST_FLAGS) $(ASYNC_FLAGS) $(UNIT_DIR)/

test-integration: ## Roda apenas testes de integração (tests/integration/)
	@echo "→ Testes de integração: fluxos entre módulos internos"
	$(PYTEST) $(PYTEST_FLAGS) $(ASYNC_FLAGS) $(INTEG_DIR)/

test-contract: ## Roda apenas testes de contrato com serviços externos (tests/contract/)
	@echo "→ Testes de contrato: requerem Langfuse, Supabase e Qdrant acessíveis"
	$(PYTEST) $(PYTEST_FLAGS) $(ASYNC_FLAGS) $(CONTRACT_DIR)/

test-e2e: ## Roda testes end-to-end (tests/e2e/) — requer infraestrutura completa
	@echo "→ Testes e2e: ciclo completo de avaliação — requer todos os serviços ativos"
	$(PYTEST) $(PYTEST_FLAGS) $(ASYNC_FLAGS) $(E2E_DIR)/

test-async: ## Roda apenas testes marcados como assíncronos em qualquer camada
	@echo "→ Filtrando apenas testes assíncronos (marcador: asyncio)"
	$(PYTEST) $(PYTEST_FLAGS) $(ASYNC_FLAGS) -m asyncio $(TEST_DIR)/


# =============================================================================
# TESTES — POR MÓDULO DO SISTEMA
# =============================================================================
#
# Cada target abaixo roda os testes de um módulo específico do src/.
# Útil durante TDD para rodar somente os testes do módulo sendo desenvolvido.
#
# =============================================================================

## Testes — Por Módulo

test-config: ## Testes do ConfigManager (Singleton de configuração)
	$(PYTEST) $(PYTEST_FLAGS) $(TEST_DIR)/ -k "config"

test-collection: ## Testes do módulo de coleta de traces (Langfuse)
	$(PYTEST) $(PYTEST_FLAGS) $(ASYNC_FLAGS) $(TEST_DIR)/ -k "collection or trace_repository"

test-extraction: ## Testes dos extractors de trace (FlowiseExtractor, LangChainExtractor)
	$(PYTEST) $(PYTEST_FLAGS) $(TEST_DIR)/ -k "extractor or extraction"

test-providers: ## Testes dos LLM providers (OpenAI, Anthropic, OpenRouter)
	$(PYTEST) $(PYTEST_FLAGS) $(ASYNC_FLAGS) $(TEST_DIR)/ -k "provider"

test-metrics: ## Testes do MetricFactory e das métricas DeepEval
	$(PYTEST) $(PYTEST_FLAGS) $(TEST_DIR)/ -k "metric"

test-evaluation: ## Testes do Evaluator principal (orquestração de avaliação)
	$(PYTEST) $(PYTEST_FLAGS) $(ASYNC_FLAGS) $(TEST_DIR)/ -k "evaluation or evaluator"

test-dataset: ## Testes do SyntheticDatasetGenerator (Synthesizer + ConversationSimulator)
	$(PYTEST) $(PYTEST_FLAGS) $(ASYNC_FLAGS) $(TEST_DIR)/ -k "dataset or synthesizer or simulator"

test-optimization: ## Testes do PromptOptimizer (GEPA / MIPROv2)
	$(PYTEST) $(PYTEST_FLAGS) $(ASYNC_FLAGS) $(TEST_DIR)/ -k "optimizer or optimization"

test-persistence: ## Testes dos Repositories (Supabase + Qdrant)
	$(PYTEST) $(PYTEST_FLAGS) $(ASYNC_FLAGS) $(TEST_DIR)/ -k "repository or persistence"

test-publisher: ## Testes do ResultPublisher (Observer — Langfuse, CSV, Qdrant, Dashboard)
	$(PYTEST) $(PYTEST_FLAGS) $(ASYNC_FLAGS) $(TEST_DIR)/ -k "publisher"

test-scheduler: ## Testes do módulo de agendamento (APScheduler)
	$(PYTEST) $(PYTEST_FLAGS) $(TEST_DIR)/ -k "scheduler"

test-dashboard: ## Testes da API do dashboard (FastAPI endpoints)
	$(PYTEST) $(PYTEST_FLAGS) $(ASYNC_FLAGS) $(TEST_DIR)/ -k "dashboard or api"


# =============================================================================
# COBERTURA DE CÓDIGO
# =============================================================================
#
# Cobertura mínima obrigatória: 80% (Princípio III — TDD)
# O target `cov` falha automaticamente se a cobertura ficar abaixo de MIN_COVERAGE.
#
# =============================================================================

## Cobertura de Código

cov: ## Roda todos os testes com relatório de cobertura (falha se < 80%)
	$(PYTEST) $(PYTEST_FLAGS) $(ASYNC_FLAGS) $(COV_FLAGS) $(TEST_DIR)/

cov-unit: ## Cobertura apenas dos testes unitários
	$(PYTEST) $(PYTEST_FLAGS) $(ASYNC_FLAGS) $(COV_FLAGS) $(UNIT_DIR)/

cov-integration: ## Cobertura dos testes de integração
	$(PYTEST) $(PYTEST_FLAGS) $(ASYNC_FLAGS) $(COV_FLAGS) $(INTEG_DIR)/

cov-html: ## Abre o relatório HTML de cobertura no navegador
	@echo "→ Abrindo htmlcov/index.html..."
	@xdg-open htmlcov/index.html 2>/dev/null || open htmlcov/index.html 2>/dev/null || \
		echo "Abra manualmente: htmlcov/index.html"


# =============================================================================
# PIPELINE DE QUALIDADE (fluxo completo de avaliação de chatbots)
# =============================================================================

## Pipeline de Qualidade

generate: ## Gera datasets sintéticos (Synthesizer + ConversationSimulator por persona)
	@echo "→ Gerando datasets a partir de config/personas.yaml e config/knowledge_base/"
	$(PYTHON) -m src.dataset.generate

evaluate: ## Roda avaliação DeepEval em todos os bots configurados em config/bots.yaml
	@echo "→ Executando avaliação — resultados salvos em Langfuse + Supabase + Qdrant"
	$(PYTHON) -m src.evaluator.run

optimize: ## Roda PromptOptimizer para um bot específico (uso: make optimize BOT=nome-do-bot)
	@echo "→ Otimizando prompt do bot: $(BOT)"
	$(PYTHON) -m src.optimization.run --bot $(BOT)


# =============================================================================
# QUALIDADE DE CÓDIGO
# =============================================================================

## Qualidade de Código

lint: ## Analisa o código com ruff (sem modificar)
	$(RUFF) check $(SRC_DIR)/ $(TEST_DIR)/

format: ## Formata o código com ruff
	$(RUFF) format $(SRC_DIR)/ $(TEST_DIR)/

check: lint ## Verifica lint + testes unitários (gate rápido antes de commit)
	$(PYTEST) $(PYTEST_FLAGS) $(UNIT_DIR)/


# =============================================================================
# INFRAESTRUTURA LOCAL (Docker Compose)
# =============================================================================

## Infraestrutura Local (Docker)

docker-up: ## Sobe todos os serviços locais (app + Langfuse + Qdrant)
	docker compose up -d

docker-down: ## Para e remove todos os containers locais
	docker compose down

docker-logs: ## Exibe os logs de todos os containers em tempo real
	docker compose logs -f

docker-build: ## Reconstrói a imagem Docker da aplicação
	docker compose build --no-cache app


# =============================================================================
# LIMPEZA
# =============================================================================

## Limpeza

clean: ## Remove artefatos de build e cache do Python
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".ruff_cache"   -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc"         -delete 2>/dev/null || true
	rm -rf htmlcov/ .coverage 2>/dev/null || true
	@echo "→ Cache limpo."

clean-cache: clean ## Alias para clean

clean-datasets: ## Remove datasets gerados (datasets/)
	@echo "→ Removendo datasets gerados em $(DATASET_DIR)/"
	rm -rf $(DATASET_DIR)/
	@echo "→ Pronto. Rode 'make generate' para regenerar."

clean-results: ## Remove resultados de avaliação exportados (resultados/)
	@echo "→ Removendo resultados em $(RESULTS_DIR)/"
	rm -rf $(RESULTS_DIR)/

clean-all: clean clean-datasets clean-results ## Remove TUDO (cache + datasets + resultados)
	@echo "→ Limpeza completa concluída."

# RAG Chatbot — developer entry point.
#
# Every verb used across the six implementation phases lives here, so that
# verification steps in docs/implementation.md can name a command instead of
# describing one. Run `make help` for the list.

SHELL := pwsh
.SHELLFLAGS := -NoProfile -Command
PY ?= python
.DEFAULT_GOAL := help

COMPOSE := docker compose

.PHONY: help
help: ## Show available targets
	@$(PY) -c "import re,pathlib;t=pathlib.Path('Makefile').read_text(encoding='utf-8');[print('  {:<22} {}'.format(m.group(1),m.group(2))) for m in re.finditer(r'^[a-zA-Z0-9_-]+:.*?## (.*)$',t,re.M)]"

# ---------------------------------------------------------------- bootstrap

.PHONY: bootstrap
bootstrap: ## Install dev dependencies and create a local .env from the template
	$(PY) -m pip install --upgrade pip
	$(PY) -m pip install -e ".[dev]"
	@if (-not (Test-Path .env)) { Copy-Item .env.example .env; Write-Host 'Created .env from template - review it before use.' }

.PHONY: install
install: ## Alias for bootstrap

# ---------------------------------------------------------------- local stack

.PHONY: up
up: ## Start the local stack (api, worker, web, postgres)
	$(COMPOSE) up -d --build
	@Write-Host 'API  http://localhost:8000'
	@Write-Host 'Docs http://localhost:8000/docs'
	@Write-Host 'Web  http://localhost:3000'

.PHONY: down
down: ## Stop the local stack
	$(COMPOSE) down

.PHONY: clean
clean: ## Stop the stack and remove local volumes
	$(COMPOSE) down -v

.PHONY: logs
logs: ## Follow logs from all services
	$(COMPOSE) logs -f

.PHONY: migrate
migrate: ## Apply database migrations
	$(COMPOSE) exec -T api $(PY) -m storage.db.migrate

.PHONY: psql
psql: ## Open a psql shell against the local database
	$(COMPOSE) exec postgres psql -U rag -d rag

# ---------------------------------------------------------------- run (no docker)

.PHONY: run-api
run-api: ## Run the API locally with uvicorn
	$(PY) -m uvicorn api.main:app --reload --port 8000

.PHONY: run-worker
run-worker: ## Run the ingestion worker locally
	$(PY) -m worker.main

.PHONY: run-web
run-web: ## Run the web app locally
	cd apps/web; npm run dev

# ---------------------------------------------------------------- verification

.PHONY: lint
lint: ## Lint Python with ruff
	$(PY) -m ruff check packages apps tests tools

.PHONY: lint-fix
lint-fix: ## Lint and auto-fix
	$(PY) -m ruff check --fix packages apps tests tools

.PHONY: format
format: ## Auto-format Python with ruff
	$(PY) -m ruff format packages apps tests tools

.PHONY: typecheck
typecheck: ## Type-check Python with mypy
	$(PY) -m mypy packages apps

.PHONY: test
test: ## Run the full test suite
	$(PY) -m pytest

.PHONY: test-unit
test-unit: ## Run unit tests only
	$(PY) -m pytest tests/unit -q

.PHONY: test-integration
test-integration: ## Run integration tests only (skips those needing a live database)
	$(PY) -m pytest tests/integration -q

.PHONY: eval
eval: ## Run the evaluation harness (expected to report zeros on an empty index)
	$(PY) -m eval.cli --dataset tests/fixtures/golden/mini.jsonl

.PHONY: eval-gate
eval-gate: ## Run the evaluation harness and enforce the NFR-12 regression gate
	$(PY) -m eval.cli --dataset evals/golden-v1.jsonl --gate

.PHONY: check-secrets
check-secrets: ## Scan the repository for committed credentials
	$(PY) tools/check_secrets.py

.PHONY: check-log-hygiene
check-log-hygiene: ## Fail if any code path can log content-bearing fields
	$(PY) tools/check_log_hygiene.py

.PHONY: check
check: lint typecheck test ## Run every gate: lint, types, tests
	@Write-Host ''
	@Write-Host 'Phase 1 gate: lint, typecheck and tests all green.'

# ---------------------------------------------------------------- phase 2
.PHONY: ingest
ingest: ## Chunk documents and populate ChromaDB
	$(PY) scripts/chunk_and_manifest.py docs/sample_docs
	$(PY) -m packages.vector.chroma_store add_chunks_from_manifest

.PHONY: query
query: ## Run the API and perform a sample query (requires .env GROQ_*)
	$(PY) -m uvicorn api.main:app --reload --port 8000 &
	sleep 2
	curl -s -X POST http://localhost:8000/api/v1/query -H "Content-Type: application/json" -d '{"question":"what is the refund policy"}' | head -n 20
	@-kill %1 2>/dev/null || true
.PHONY: help keys up down logs ps seed demo test test-unit test-security test-integration lint type-check bandit audit clean

COMPOSE := docker compose -f infra/docker/docker-compose.yml --env-file .env

help:
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "%-22s %s\n", $$1, $$2}'

keys: ## Generate dev secrets (JWT keypair + symmetric keys)
	@mkdir -p secrets
	@python scripts/generate_keys.py

up: keys ## Build and start the full stack
	$(COMPOSE) up -d --build

down: ## Stop the stack (keeps volumes)
	$(COMPOSE) down

logs: ## Tail app logs
	$(COMPOSE) logs -f app

ps: ## Show service status
	$(COMPOSE) ps

seed: ## Seed demo users and accounts
	$(COMPOSE) exec app python -m scripts.seed_demo
	$(COMPOSE) exec app python -m scripts.seed_tpps

demo: ## Run the scripted end-to-end demo
	$(COMPOSE) exec app python -m scripts.demo_scenario

test: test-unit test-security ## Default: fast tests only (no docker required)

test-unit: ## Unit tests
	pytest -m unit -q

test-security: ## Security-focused tests
	pytest -m security -q

test-integration: ## Integration tests (requires `make up && make seed`)
	INTEGRATION_API=http://localhost:8000 pytest -m integration -q

lint: ## Ruff lint + format check
	ruff check .
	ruff format --check .

type-check: ## mypy
	mypy app

bandit: ## Static security scan
	bandit -r app -ll

audit: ## Dependency vulnerability audit
	pip-audit

clean: ## Remove caches and __pycache__
	find . -type d -name __pycache__ -exec rm -rf {} +
	rm -rf .pytest_cache .mypy_cache .ruff_cache htmlcov coverage.xml

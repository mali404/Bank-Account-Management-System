# AgentBank-Sec Testbed — developer and CI entrypoints.
# Requires GNU make. Run `make` or `make help` for the target list.

SHELL := /usr/bin/env bash
.DEFAULT_GOAL := help

# Compose project name. Override with AGENTBANK_PROJECT=... (or PROJECT=...) so
# several checkouts can run side by side on one host. Exported so the helper
# scripts (bootstrap.sh, check_health.sh, export-root.sh) agree with the Makefile.
PROJECT ?= $(or $(AGENTBANK_PROJECT),agentbank)
export AGENTBANK_PROJECT := $(PROJECT)
COMPOSE_FILE := deploy/compose.yaml
COMPOSE := docker compose --project-name $(PROJECT) --env-file .env -f $(COMPOSE_FILE)
COMPOSE_OVERLAYS := deploy/compose.llm.yaml deploy/compose.obs.yaml deploy/compose.mojaloop.yaml

.PHONY: help bootstrap up down ps logs health pki-root test test-compose test-iso lint format \
        typecheck check compose-config clean seed reset bench report controls-check \
        iso-gen iso-setup xsd-install xsd-verify xsd-fetch

help: ## Show this help
	@echo "AgentBank-Sec Testbed — make targets:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

bootstrap: ## Check prerequisites, create .env (with generated secrets), uv sync, pull images
	@bash scripts/bootstrap.sh

up: ## Start core infra and wait until every service is healthy
	@$(COMPOSE) up -d --wait --wait-timeout 300
	@bash scripts/check_health.sh

down: ## Stop and remove the stack
	@$(COMPOSE) down

ps: ## Show compose service status
	@$(COMPOSE) ps

logs: ## Tail compose logs
	@$(COMPOSE) logs -f

health: ## Print the health of each service
	@bash scripts/check_health.sh

pki-root: ## Export the step-ca root cert (stack must be running); not required by `up`
	@bash deploy/pki/export-root.sh

ISO_GEN_MARKER := libs/agentbank_iso/src/agentbank_iso/gen/pacs008_001_08

test: ## Run unit tests (no docker/network; needs `make bootstrap` or `make iso-setup` once)
	@test -d $(ISO_GEN_MARKER) || { echo "ISO bindings missing: run 'make iso-setup' (or 'make bootstrap')"; exit 1; }
	@uv run pytest

test-compose: ## Live checks against the running stack (docker required)
	@uv run pytest -m compose

test-iso: ## Run the ISO 20022 acceptance tests (1,000 Hypothesis cases/message)
	@uv run pytest tests/unit/iso --hypothesis-show-statistics

iso-gen: ## Regenerate the xsdata ISO bindings from iso20022/xsd (deterministic)
	@bash scripts/gen_iso_bindings.sh

iso-setup: xsd-install iso-gen ## Download + verify the ISO XSDs, then generate the bindings

xsd-install: ## Download missing ISO XSDs from iso20022.org and verify SHA-256 (network)
	@python3 scripts/fetch_xsd.py install

xsd-verify: ## Offline: recompute SHA-256 of the local XSDs vs MANIFEST.yaml
	@python3 scripts/fetch_xsd.py verify

xsd-fetch: ## Re-download XSDs to a temp dir and compare hashes only (network)
	@python3 scripts/fetch_xsd.py fetch

lint: ## ruff check + ruff format --check
	@uv run ruff check .
	@uv run ruff format --check .

format: ## Apply ruff format and import fixes
	@uv run ruff format .
	@uv run ruff check --fix .

typecheck: ## mypy (strict)
	@uv run mypy

check: lint typecheck test ## Lint, typecheck and test

compose-config: ## Validate all compose files
	@$(COMPOSE) config -q
	@for overlay in $(COMPOSE_OVERLAYS); do \
		echo "validating $$overlay"; \
		$(COMPOSE) -f $$overlay config -q; \
	done

clean: ## Remove caches and generated artifacts
	@rm -rf .pytest_cache .ruff_cache .mypy_cache
	@find . -type d -name __pycache__ -prune -exec rm -rf {} + 2>/dev/null || true

# --- Targets for later milestones (fail loudly so nobody mistakes them for working) ---

SEED ?= 42

seed: ## (M2) Seed synthetic customers, history and the reset snapshot
	@uv run python data/generator/generate.py --seed $(SEED)

reset: ## (M2) Restore the seeded snapshot (budget 30s)
	@uv run python scripts/reset_state.py

bench: ## (M5) Run bankbench evaluation — not implemented yet
	@echo "bench: not implemented yet (milestone M5)"; exit 1

report: ## (M5) Render a run report — not implemented yet
	@echo "report: not implemented yet (milestone M5)"; exit 1

controls-check: ## (M7) Verify NIST controls against OSCAL — not implemented yet
	@echo "controls-check: not implemented yet (milestone M7)"; exit 1

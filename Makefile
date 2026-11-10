.PHONY: help init migrate test-unit test-property test-integration lint clean reproduce

help: ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-18s %s\n", $$1, $$2}'

init: ## Create local virtualenv and install dev dependencies
	python -m venv .venv
	.venv/bin/python -m pip install -e ".[dev]"

migrate: ## Run versioned migrations
	@python scripts/migrations/runner.py

test-unit: ## Run unit tests
	@python -m pytest tests/unit -q

test-property: ## Run property tests
	@python -m pytest tests/property -q

test-integration: ## Run integration tests (requires Docker PostgreSQL 16)
	@python -m pytest tests/integration -q

lint: ## Run lint
	@python -m ruff check .

clean: ## Remove Python caches
	@rm -rf .pytest_cache .ruff_cache .mypy_cache tests/.pytest_cache

reproduce: ## Deterministic pipeline from an empty database (writes RESULTS.md)
	@python scripts/reproduce.py

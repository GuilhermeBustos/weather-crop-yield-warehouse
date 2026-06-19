.DEFAULT_GOAL := help
UV := uv

.PHONY: help install lint fmt sql-lint test pre-commit

help: ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

install: ## Create the venv (Python 3.12), install dev tooling + git hooks
	$(UV) python install 3.12
	$(UV) sync
	git config --unset-all core.hooksPath 2>/dev/null || true
	$(UV) run pre-commit install

lint: ## Lint + format-check Python (ruff)
	$(UV) run ruff check .
	$(UV) run ruff format --check .

fmt: ## Auto-fix + format Python (ruff)
	$(UV) run ruff check --fix .
	$(UV) run ruff format .

sql-lint: ## Lint SQL (sqlfluff) — activates once dbt models exist (Phase 3)
	$(UV) run sqlfluff lint dbt/models || true

test: ## Run unit tests (pytest)
	$(UV) run pytest

pre-commit: ## Run all pre-commit hooks against the whole tree
	$(UV) run pre-commit run --all-files

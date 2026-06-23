.DEFAULT_GOAL := help
UV := uv
TF := terraform
TF_DIR := infra/terraform

.PHONY: help install lint fmt sql-lint test pre-commit \
	seed ingest-weather ingest-yield \
	tf-init tf-fmt tf-validate tf-plan tf-apply tf-destroy

help: ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

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

seed: ## Build the county-centroid seed CSV (dbt/seeds/county_centroids.csv)
	$(UV) run python -m wcy_ingestion seed

ingest-weather: ## Run the weather pipeline (extract -> bronze -> raw.weather_daily)
	$(UV) run python -m wcy_ingestion weather

ingest-yield: ## Run the yield pipeline (extract -> bronze -> raw.nass_yield)
	$(UV) run python -m wcy_ingestion yield

tf-init: ## Init Terraform (remote state via backend.hcl)
	$(TF) -chdir=$(TF_DIR) init -backend-config=backend.hcl

tf-fmt: ## Format Terraform files
	$(TF) -chdir=$(TF_DIR) fmt -recursive

tf-validate: ## Validate Terraform (no backend or credentials needed)
	$(TF) -chdir=$(TF_DIR) init -backend=false -input=false >/dev/null && $(TF) -chdir=$(TF_DIR) validate

tf-plan: ## Plan the dev environment
	$(TF) -chdir=$(TF_DIR) plan -var-file=dev.tfvars

tf-apply: ## Apply the dev environment
	$(TF) -chdir=$(TF_DIR) apply -var-file=dev.tfvars

tf-destroy: ## Destroy the dev environment
	$(TF) -chdir=$(TF_DIR) destroy -var-file=dev.tfvars

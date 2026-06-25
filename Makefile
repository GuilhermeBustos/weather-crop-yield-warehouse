.DEFAULT_GOAL := help
UV := uv
TF := terraform
TF_DIR := infra/terraform
DBT_PROFILES_DIR := dbt/profiles
export DBT_PROFILES_DIR

.PHONY: help install lint fmt sql-lint test pre-commit \
	seed ingest-weather ingest-yield \
	dbt-deps dbt-seed dbt-build dbt-test dbt-docs \
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

sql-lint: ## Lint SQL with the dbt templater (sqlfluff)
	$(UV) run sqlfluff lint dbt/models

test: ## Run unit tests (pytest)
	$(UV) run pytest

pre-commit: ## Run all pre-commit hooks against the whole tree
	$(UV) run pre-commit run --all-files

dbt-deps: ## Install dbt packages declared in packages.yml
	$(UV) run dbt deps --project-dir dbt --profiles-dir dbt/profiles

dbt-seed: ## Load seed CSVs into BigQuery (county_centroids)
	$(UV) run dbt seed --project-dir dbt --profiles-dir dbt/profiles

dbt-build: ## Run all dbt models + tests (full build)
	$(UV) run dbt build --project-dir dbt --profiles-dir dbt/profiles

dbt-test: ## Run dbt tests only (no model rebuild)
	$(UV) run dbt test --project-dir dbt --profiles-dir dbt/profiles

dbt-docs: ## Generate dbt docs (HTML + manifest)
	$(UV) run dbt docs generate --project-dir dbt --profiles-dir dbt/profiles

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

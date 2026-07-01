variable "project_id" {
  description = "GCP project id that owns all resources."
  type        = string
}

variable "region" {
  description = "Region for regional resources (GCS bronze bucket, Composer)."
  type        = string
  default     = "us-central1"
}

variable "bq_location" {
  description = "BigQuery dataset location. 'US' multi-region by default."
  type        = string
  default     = "US"
}

variable "labels" {
  description = "Labels applied to every resource via the provider default_labels."
  type        = map(string)
  default = {
    project = "wcy"
    env     = "dev"
  }
}

# ---- GCS ---------------------------------------------------------------------

variable "bronze_retention_days" {
  description = "Age in days after which objects in the bronze bucket are deleted."
  type        = number
  default     = 365
}

variable "bucket_force_destroy" {
  description = "Let `terraform destroy` delete the bronze bucket even when non-empty. Keep true in dev, false in prod."
  type        = bool
  default     = true
}

# ---- BigQuery ----------------------------------------------------------------

# Dataset ids: name the BigQuery datasets and feed the dbt/Composer env vars.
variable "raw_dataset" {
  description = "BigQuery dataset id for the raw (loaded bronze) layer."
  type        = string
  default     = "raw"
}

variable "staging_dataset" {
  description = "BigQuery dataset id for the dbt staging layer."
  type        = string
  default     = "staging"
}

variable "marts_dataset" {
  description = "BigQuery dataset id for the dbt marts layer."
  type        = string
  default     = "marts"
}

variable "dbt_ci_dataset" {
  description = "BigQuery dataset id for ephemeral dbt CI builds (tables auto-expire)."
  type        = string
  default     = "dbt_ci"
}

variable "dataset_force_destroy" {
  description = "Let `terraform destroy` delete datasets that still contain tables. Keep true in dev, false in prod."
  type        = bool
  default     = true
}

# ---- Composer -----------------------------------

variable "enable_composer" {
  description = "Provision the Cloud Composer environment. Left false until needed — Composer is the largest fixed cost and runs 24/7; Phase 4 keeps it ephemeral."
  type        = bool
  default     = false
}

variable "composer_env_name" {
  description = "Name of the Composer environment."
  type        = string
  default     = "wcy-composer"
}

variable "composer_image_version" {
  description = "Composer image, e.g. 'composer-3-airflow-3.x.x-build.x' (Airflow 3 requires Composer 3). REQUIRED before enabling Composer — list via the Composer REST API (imageVersions endpoint) or `gcloud composer images list --location=<region>` on an up-to-date SDK. No default to avoid pinning a stale/invalid image."
  type        = string
  default     = null
}

variable "composer_environment_size" {
  description = "Composer environment size: ENVIRONMENT_SIZE_SMALL | ENVIRONMENT_SIZE_MEDIUM | ENVIRONMENT_SIZE_LARGE."
  type        = string
  default     = "ENVIRONMENT_SIZE_SMALL"
}

variable "nass_secret_id" {
  description = "Secret Manager secret *id* holding the NASS API key; passed to Composer as WCY_NASS_SECRET_ID."
  type        = string
  default     = "nass-api-key"
}

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

variable "datasets" {
  description = "BigQuery datasets to create, keyed by dataset id."
  type = map(object({
    description                   = string
    default_table_expiration_days = optional(number)
  }))
  default = {
    raw = {
      description = "Bronze GCS files loaded into BigQuery, lightly typed."
    }
    staging = {
      description = "dbt staging views: renamed, cast, deduplicated."
    }
    marts = {
      description = "dbt marts: modeled facts and dimensions for analysis."
    }
    dbt_ci = {
      description                   = "Ephemeral dbt CI builds; tables auto-expire."
      default_table_expiration_days = 7
    }
  }
}

variable "dataset_force_destroy" {
  description = "Let `terraform destroy` delete datasets that still contain tables. Keep true in dev, false in prod."
  type        = bool
  default     = true
}

# ---- IAM ---------------------------------------------------------------------

variable "pipeline_sa_account_id" {
  description = "Account id of the pipeline service account."
  type        = string
  default     = "wcy-pipeline"
}

# ---- Composer (deferred — see composer.tf) -----------------------------------

variable "enable_composer" {
  description = "Provision the Cloud Composer 2 environment. Left false until Phase 4 — Composer is the largest fixed cost and runs 24/7."
  type        = bool
  default     = false
}

variable "composer_env_name" {
  description = "Name of the Composer 2 environment."
  type        = string
  default     = "wcy-composer"
}

variable "composer_image_version" {
  description = "Composer 2 image, e.g. 'composer-2.x.x-airflow-2.x.x'. REQUIRED before enabling Composer — verify with `gcloud composer images list --location=<region>`. No default to avoid pinning a stale/invalid image."
  type        = string
  default     = null
}

variable "composer_environment_size" {
  description = "Composer 2 environment size: ENVIRONMENT_SIZE_SMALL | ENVIRONMENT_SIZE_MEDIUM | ENVIRONMENT_SIZE_LARGE."
  type        = string
  default     = "ENVIRONMENT_SIZE_SMALL"
}

resource "google_composer_environment" "main" {
  count = var.enable_composer ? 1 : 0

  name   = var.composer_env_name
  region = var.region

  config {
    software_config {
      image_version = var.composer_image_version

      pypi_packages = {
        "astronomer-cosmos" = ">=1.8.0,<2.0.0"
        "dbt-bigquery"      = ">=1.8.0,<2.0.0"
        "pydantic-settings" = ">=2.7"
        "httpx"             = ">=0.28"
        "tenacity"          = ">=9.0"
      }

      # Non-secret config only. The NASS API key is NOT here: it stays in Secret
      # Manager and is fetched at runtime by wcy_ingestion via the node SA.
      env_variables = {
        # dbt / cosmos — ids only; auth is ADC via the node SA.
        DBT_BQ_PROJECT      = var.project_id
        DBT_RAW_DATASET     = var.raw_dataset
        DBT_STAGING_DATASET = var.staging_dataset
        DBT_MARTS_DATASET   = var.marts_dataset
        DBT_BQ_LOCATION     = var.bq_location
        # The dbt project is synced under the DAG bucket by `make composer-deploy` (T3).
        DBT_PROFILES_DIR = "/home/airflow/gcs/dags/dbt/profiles"

        # wcy_ingestion Settings (WCY_ prefix). bronze_bucket + nass_secret_id are
        # required (no defaults); the rest pin the locked slice's config.
        WCY_PROJECT_ID     = var.project_id
        WCY_BRONZE_BUCKET  = google_storage_bucket.bronze.name
        WCY_RAW_DATASET    = var.raw_dataset
        WCY_REGION         = var.region
        WCY_NASS_SECRET_ID = var.nass_secret_id
      }
    }

    environment_size = var.composer_environment_size

    node_config {
      service_account = google_service_account.pipeline.email
    }
  }
}

# The environment's service account needs composer.worker — only when enabled.
resource "google_project_iam_member" "pipeline_composer_worker" {
  count = var.enable_composer ? 1 : 0

  project = var.project_id
  role    = "roles/composer.worker"
  member  = "serviceAccount:${google_service_account.pipeline.email}"
}

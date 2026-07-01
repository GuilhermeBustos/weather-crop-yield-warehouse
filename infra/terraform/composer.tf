# The project's default Compute Engine SA. Composer's node pool now runs
# under this SA (instead of the custom pipeline SA) to rule out custom-SA
# logging/monitoring issues.
data "google_compute_default_service_account" "default" {
  project = var.project_id
}

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

    # Composer's API requires an explicit service account — it will not fall
    # back to the default Compute Engine SA on its own, so pass its email
    # through rather than omitting node_config.service_account.
    node_config {
      service_account = data.google_compute_default_service_account.default.email
    }
  }
}

# --- Default Compute Engine SA grants ---------------------------------------
# Composer's node pool now runs as the default Compute Engine SA rather than
# the custom pipeline SA, so it needs the same DAG-facing permissions the
# pipeline SA carries in iam.tf: BigQuery job/data access, bronze bucket
# object access, and Secret Manager read (for the NASS API key).

resource "google_project_iam_member" "default_sa_composer_worker" {
  count = var.enable_composer ? 1 : 0

  project = var.project_id
  role    = "roles/composer.worker"
  member  = "serviceAccount:${data.google_compute_default_service_account.default.email}"
}

resource "google_project_iam_member" "default_sa_bq_job_user" {
  count = var.enable_composer ? 1 : 0

  project = var.project_id
  role    = "roles/bigquery.jobUser"
  member  = "serviceAccount:${data.google_compute_default_service_account.default.email}"
}

resource "google_bigquery_dataset_iam_member" "default_sa_data_editor" {
  for_each = var.enable_composer ? google_bigquery_dataset.this : {}

  dataset_id = each.value.dataset_id
  role       = "roles/bigquery.dataEditor"
  member     = "serviceAccount:${data.google_compute_default_service_account.default.email}"
}

resource "google_storage_bucket_iam_member" "default_sa_bronze_object_admin" {
  count = var.enable_composer ? 1 : 0

  bucket = google_storage_bucket.bronze.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${data.google_compute_default_service_account.default.email}"
}

resource "google_project_iam_member" "default_sa_secret_accessor" {
  count = var.enable_composer ? 1 : 0

  project = var.project_id
  role    = "roles/secretmanager.secretAccessor"
  member  = "serviceAccount:${data.google_compute_default_service_account.default.email}"
}

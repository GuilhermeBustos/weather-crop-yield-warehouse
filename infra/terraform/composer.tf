# Cloud Composer 2 (Airflow) environment — Phase 4.
#
# Deferred behind `enable_composer` (default false): Composer is the largest fixed
# cost and runs 24/7, and milestones M1/M2 need no orchestration. To enable at
# Phase 4: set a verified `composer_image_version`
# (`gcloud composer images list --location=<region>`), confirm the Composer API is
# enabled, then set `enable_composer = true`.
resource "google_composer_environment" "main" {
  count = var.enable_composer ? 1 : 0

  name   = var.composer_env_name
  region = var.region

  config {
    software_config {
      image_version = var.composer_image_version
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

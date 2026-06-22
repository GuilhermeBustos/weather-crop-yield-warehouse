# Pipeline service account: used by ingestion, dbt, and (later) Composer tasks.
resource "google_service_account" "pipeline" {
  account_id   = var.pipeline_sa_account_id
  display_name = "WCY pipeline service account"
  description  = "Runs ingestion, dbt builds, and Composer tasks. Least privilege."
}

# --- BigQuery: project-level job runner + dataset-level data editor ---
# jobUser must be granted at the project level; dataEditor is scoped per dataset
# rather than project-wide to keep the SA least-privilege.

resource "google_project_iam_member" "pipeline_bq_job_user" {
  project = var.project_id
  role    = "roles/bigquery.jobUser"
  member  = "serviceAccount:${google_service_account.pipeline.email}"
}

resource "google_bigquery_dataset_iam_member" "pipeline_data_editor" {
  for_each = google_bigquery_dataset.this

  dataset_id = each.value.dataset_id
  role       = "roles/bigquery.dataEditor"
  member     = "serviceAccount:${google_service_account.pipeline.email}"
}

# --- GCS: object admin on the bronze bucket only (not project-wide) ---

resource "google_storage_bucket_iam_member" "pipeline_bronze_object_admin" {
  bucket = google_storage_bucket.bronze.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.pipeline.email}"
}

# --- Secret Manager: read secrets such as the NASS API key ---
# Project-level for now; scope to the specific secret in Phase 4 once it exists.
resource "google_project_iam_member" "pipeline_secret_accessor" {
  project = var.project_id
  role    = "roles/secretmanager.secretAccessor"
  member  = "serviceAccount:${google_service_account.pipeline.email}"
}

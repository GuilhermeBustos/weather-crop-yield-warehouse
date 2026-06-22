output "bronze_bucket" {
  description = "Name of the bronze GCS landing bucket."
  value       = google_storage_bucket.bronze.name
}

output "dataset_ids" {
  description = "Map of dataset key => fully-qualified BigQuery dataset id."
  value = {
    for k, ds in google_bigquery_dataset.this : k => "${var.project_id}.${ds.dataset_id}"
  }
}

output "pipeline_service_account_email" {
  description = "Email of the pipeline service account."
  value       = google_service_account.pipeline.email
}

output "composer_airflow_uri" {
  description = "Airflow web UI URI (null until enable_composer = true)."
  value       = try(google_composer_environment.main[0].config[0].airflow_uri, null)
}

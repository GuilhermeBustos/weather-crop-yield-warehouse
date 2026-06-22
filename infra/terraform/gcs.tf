# Bronze landing bucket: raw, as-is source files (Parquet) before load into BigQuery.
resource "google_storage_bucket" "bronze" {
  name     = "${var.project_id}-bronze"
  location = var.region

  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  force_destroy               = var.bucket_force_destroy

  # Expire old raw files so re-landable source data does not accumulate cost.
  lifecycle_rule {
    condition {
      age = var.bronze_retention_days
    }
    action {
      type = "Delete"
    }
  }
}

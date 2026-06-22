# Remote state in GCS. Partial config: the bucket name is supplied at init time
# via `-backend-config=backend.hcl`. The state bucket is created manually before
# the first init (Terraform cannot create the bucket that holds its own state) —
# see README.md. The GCS backend provides state locking automatically.
terraform {
  backend "gcs" {
    prefix = "weather-crop-yield"
  }
}

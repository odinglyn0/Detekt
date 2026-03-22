resource "google_storage_bucket" "dtkt_media" {
  name          = "${var.dtkt_bucket_name}-${var.dtkt_gcp_project}"
  location      = var.dtkt_gcp_region
  force_destroy = true

  uniform_bucket_level_access = true

  lifecycle_rule {
    action {
      type = "Delete"
    }
    condition {
      age = 7
    }
  }

  labels = {
    dtkt-app = "worker"
    dtkt-env = "prod"
  }
}

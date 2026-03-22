resource "google_pubsub_topic" "dtkt_mentions_dlq" {
  name = "dtkt-mentions-dlq"

  message_retention_duration = "604800s"
}

resource "google_pubsub_subscription" "dtkt_scanner" {
  name  = "dtkt-scanner-sub"
  topic = google_pubsub_topic.dtkt_mentions.name

  ack_deadline_seconds       = 120
  message_retention_duration = "604800s"

  expiration_policy {
    ttl = ""
  }

  retry_policy {
    minimum_backoff = "10s"
    maximum_backoff = "600s"
  }

  dead_letter_policy {
    dead_letter_topic     = google_pubsub_topic.dtkt_mentions_dlq.id
    max_delivery_attempts = 5
  }
}

resource "google_pubsub_subscription" "dtkt_dlq_sub" {
  name  = "dtkt-dlq-sub"
  topic = google_pubsub_topic.dtkt_mentions_dlq.name

  ack_deadline_seconds       = 60
  message_retention_duration = "604800s"

  expiration_policy {
    ttl = ""
  }
}

resource "google_service_account" "dtkt_scanner" {
  account_id   = "dtkt-scanner"
  display_name = "detekt scanner service account"
}

resource "google_project_iam_member" "dtkt_scanner_pubsub_subscriber" {
  project = var.dtkt_gcp_project
  role    = "roles/pubsub.subscriber"
  member  = "serviceAccount:${google_service_account.dtkt_scanner.email}"
}

resource "google_project_iam_member" "dtkt_scanner_pubsub_viewer" {
  project = var.dtkt_gcp_project
  role    = "roles/pubsub.viewer"
  member  = "serviceAccount:${google_service_account.dtkt_scanner.email}"
}

resource "google_project_iam_member" "dtkt_scanner_storage" {
  project = var.dtkt_gcp_project
  role    = "roles/storage.objectViewer"
  member  = "serviceAccount:${google_service_account.dtkt_scanner.email}"
}

resource "google_project_iam_member" "dtkt_scanner_firestore" {
  project = var.dtkt_gcp_project
  role    = "roles/datastore.user"
  member  = "serviceAccount:${google_service_account.dtkt_scanner.email}"
}

resource "google_project_iam_member" "dtkt_scanner_token_creator" {
  project = var.dtkt_gcp_project
  role    = "roles/iam.serviceAccountTokenCreator"
  member  = "serviceAccount:${google_service_account.dtkt_scanner.email}"
}

resource "google_firestore_database" "dtkt_default" {
  project     = var.dtkt_gcp_project
  name        = "(default)"
  location_id = var.dtkt_gcp_region
  type        = "FIRESTORE_NATIVE"
}

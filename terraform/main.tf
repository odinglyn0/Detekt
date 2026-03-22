terraform {
  required_version = ">= 1.5"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}

provider "google" {
  project = var.dtkt_gcp_project
  region  = var.dtkt_gcp_region
}

locals {
  dtkt_poller_image  = var.dtkt_docker_image != "" ? var.dtkt_docker_image : "gcr.io/${var.dtkt_gcp_project}/dtkt-poller:latest"
  dtkt_scanner_image = var.dtkt_scanner_docker_image != "" ? var.dtkt_scanner_docker_image : "gcr.io/${var.dtkt_gcp_project}/dtkt-scanner:latest"
}

resource "google_pubsub_topic" "dtkt_mentions" {
  name = var.dtkt_pubsub_topic

  message_retention_duration = "604800s"
}

resource "google_service_account" "dtkt_poller" {
  account_id   = "dtkt-poller"
  display_name = "detekt poller service account"
}

resource "google_project_iam_member" "dtkt_poller_pubsub" {
  project = var.dtkt_gcp_project
  role    = "roles/pubsub.publisher"
  member  = "serviceAccount:${google_service_account.dtkt_poller.email}"
}

resource "google_project_iam_member" "dtkt_poller_storage" {
  project = var.dtkt_gcp_project
  role    = "roles/storage.objectAdmin"
  member  = "serviceAccount:${google_service_account.dtkt_poller.email}"
}

data "google_project" "dtkt_current" {}

resource "google_pubsub_topic_iam_member" "dtkt_dlq_publisher" {
  topic  = google_pubsub_topic.dtkt_mentions_dlq.name
  role   = "roles/pubsub.publisher"
  member = "serviceAccount:service-${data.google_project.dtkt_current.number}@gcp-sa-pubsub.iam.gserviceaccount.com"
}

resource "google_pubsub_subscription_iam_member" "dtkt_scanner_sub_subscriber" {
  subscription = google_pubsub_subscription.dtkt_scanner.name
  role         = "roles/pubsub.subscriber"
  member       = "serviceAccount:service-${data.google_project.dtkt_current.number}@gcp-sa-pubsub.iam.gserviceaccount.com"
}

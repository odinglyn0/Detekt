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
  dtkt_worker_image = var.dtkt_worker_docker_image != "" ? var.dtkt_worker_docker_image : "gcr.io/${var.dtkt_gcp_project}/dtkt-worker:latest"
}

resource "google_service_account" "dtkt_worker" {
  account_id   = "dtkt-worker"
  display_name = "detekt worker service account"
}

resource "google_project_iam_member" "dtkt_worker_storage_admin" {
  project = var.dtkt_gcp_project
  role    = "roles/storage.objectAdmin"
  member  = "serviceAccount:${google_service_account.dtkt_worker.email}"
}

resource "google_project_iam_member" "dtkt_worker_firestore" {
  project = var.dtkt_gcp_project
  role    = "roles/datastore.user"
  member  = "serviceAccount:${google_service_account.dtkt_worker.email}"
}

resource "google_project_iam_member" "dtkt_worker_token_creator" {
  project = var.dtkt_gcp_project
  role    = "roles/iam.serviceAccountTokenCreator"
  member  = "serviceAccount:${google_service_account.dtkt_worker.email}"
}

resource "google_firestore_database" "dtkt_default" {
  project     = var.dtkt_gcp_project
  name        = "(default)"
  location_id = var.dtkt_gcp_region
  type        = "FIRESTORE_NATIVE"
}

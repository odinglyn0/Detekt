resource "google_compute_instance" "dtkt_scanner" {
  name         = "dtkt-scanner"
  machine_type = var.dtkt_scanner_vm_machine_type
  zone         = var.dtkt_gcp_zone

  tags = ["dtkt-scanner"]

  boot_disk {
    initialize_params {
      image = "cos-cloud/cos-stable"
      size  = var.dtkt_vm_disk_size
      type  = "pd-ssd"
    }
  }

  network_interface {
    network = "default"

    access_config {}
  }

  service_account {
    email  = google_service_account.dtkt_scanner.email
    scopes = ["cloud-platform"]
  }

  metadata = {
    gce-container-declaration = yamlencode({
      spec = {
        containers = [{
          image = local.dtkt_scanner_image
          name  = "dtkt-scanner"
          env = [
            {
              name  = "DOPPLER_TOKEN"
              value = var.dtkt_scanner_doppler_token
            },
            {
              name  = "DTKT_GCP_PROJECT"
              value = var.dtkt_gcp_project
            },
            {
              name  = "DTKT_PUBSUB_SUBSCRIPTION"
              value = google_pubsub_subscription.dtkt_scanner.name
            },
            {
              name  = "DTKT_BUCKET_NAME"
              value = google_storage_bucket.dtkt_media.name
            },
            {
              name  = "DTKT_FIRESTORE_SCANS_COLLECTION"
              value = var.dtkt_firestore_scans_collection
            },
          ]
        }]
        restartPolicy = "Always"
      }
    })
  }

  scheduling {
    automatic_restart   = true
    on_host_maintenance = "MIGRATE"
    preemptible         = false
  }

  allow_stopping_for_update = true

  labels = {
    dtkt-app = "scanner"
    dtkt-env = "prod"
  }
}

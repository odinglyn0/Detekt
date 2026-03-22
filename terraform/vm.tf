resource "google_compute_instance" "dtkt_poller" {
  name         = "dtkt-poller"
  machine_type = var.dtkt_vm_machine_type
  zone         = var.dtkt_gcp_zone

  tags = ["dtkt-poller"]

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
    email  = google_service_account.dtkt_poller.email
    scopes = ["cloud-platform"]
  }

  metadata = {
    gce-container-declaration = yamlencode({
      spec = {
        containers = [{
          image = local.dtkt_poller_image
          name  = "dtkt-poller"
          env = [
            {
              name  = "DOPPLER_TOKEN"
              value = var.dtkt_doppler_token
            },
            {
              name  = "DTKT_GCP_PROJECT"
              value = var.dtkt_gcp_project
            },
            {
              name  = "DTKT_PUBSUB_TOPIC"
              value = var.dtkt_pubsub_topic
            },
            {
              name  = "DTKT_BUCKET_NAME"
              value = google_storage_bucket.dtkt_media.name
            },
            {
              name  = "DTKT_FIRESTORE_COMMENTS_COLLECTION"
              value = var.dtkt_firestore_comments_collection
            },
            {
              name  = "DTKT_FIRESTORE_CIRCUIT_COLLECTION"
              value = var.dtkt_firestore_circuit_collection
            },
            {
              name  = "DTKT_FIRESTORE_CIRCUIT_DOC"
              value = var.dtkt_firestore_circuit_doc
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
    dtkt-app = "poller"
    dtkt-env = "prod"
  }
}

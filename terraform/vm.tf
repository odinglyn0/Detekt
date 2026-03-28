resource "google_compute_instance" "dtkt_worker" {
  name         = "dtkt-worker"
  machine_type = var.dtkt_vm_machine_type
  zone         = var.dtkt_gcp_zone

  tags = ["dtkt-worker"]

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
    email  = google_service_account.dtkt_worker.email
    scopes = ["cloud-platform"]
  }

  metadata = {
    gce-container-declaration = yamlencode({
      apiVersion = "v1"
      kind       = "Pod"
      metadata = {
        name = "dtkt-worker"
      }
      spec = {
        containers = [{
          image = local.dtkt_worker_image
          name  = "dtkt-worker"
          env = [
            {
              name  = "DOPPLER_TOKEN"
              value = var.dtkt_doppler_token
            },
            {
              name  = "DTKT_GCP_PROJECT"
              value = var.dtkt_gcp_project
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
    dtkt-app = "worker"
    dtkt-env = "prod"
  }
}

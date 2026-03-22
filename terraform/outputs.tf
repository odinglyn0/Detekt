output "dtkt_worker_vm_ip" {
  value       = google_compute_instance.dtkt_worker.network_interface[0].access_config[0].nat_ip
  description = "External IP of the worker VM"
}

output "dtkt_worker_service_account_email" {
  value       = google_service_account.dtkt_worker.email
  description = "Service account email for the worker"
}

output "dtkt_bucket_name" {
  value       = google_storage_bucket.dtkt_media.name
  description = "GCS bucket name for downloaded media"
}

output "dtkt_bucket_url" {
  value       = google_storage_bucket.dtkt_media.url
  description = "GCS bucket URL"
}

output "dtkt_vm_ip" {
  value       = google_compute_instance.dtkt_poller.network_interface[0].access_config[0].nat_ip
  description = "External IP of the poller VM"
}

output "dtkt_pubsub_topic_name" {
  value       = google_pubsub_topic.dtkt_mentions.name
  description = "Pub/Sub topic name for mentions"
}

output "dtkt_pubsub_topic_id" {
  value       = google_pubsub_topic.dtkt_mentions.id
  description = "Pub/Sub topic full ID"
}

output "dtkt_service_account_email" {
  value       = google_service_account.dtkt_poller.email
  description = "Service account email for the poller"
}

output "dtkt_bucket_name" {
  value       = google_storage_bucket.dtkt_media.name
  description = "GCS bucket name for downloaded media"
}

output "dtkt_bucket_url" {
  value       = google_storage_bucket.dtkt_media.url
  description = "GCS bucket URL"
}

output "dtkt_scanner_vm_ip" {
  value       = google_compute_instance.dtkt_scanner.network_interface[0].access_config[0].nat_ip
  description = "External IP of the scanner VM"
}

output "dtkt_scanner_service_account_email" {
  value       = google_service_account.dtkt_scanner.email
  description = "Service account email for the scanner"
}

output "dtkt_scanner_subscription" {
  value       = google_pubsub_subscription.dtkt_scanner.name
  description = "Scanner Pub/Sub subscription name"
}

output "dtkt_dlq_topic" {
  value       = google_pubsub_topic.dtkt_mentions_dlq.name
  description = "Dead letter queue topic name"
}

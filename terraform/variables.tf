variable "dtkt_gcp_project" {
  type        = string
  description = "GCP project ID"
}

variable "dtkt_gcp_region" {
  type        = string
  default     = "europe-west2"
  description = "GCP region (London)"
}

variable "dtkt_gcp_zone" {
  type        = string
  default     = "europe-west2-a"
  description = "GCP zone within London region"
}

variable "dtkt_vm_machine_type" {
  type        = string
  default     = "e2-small"
  description = "VM machine type"
}

variable "dtkt_vm_disk_size" {
  type        = number
  default     = 20
  description = "Boot disk size in GB"
}

variable "dtkt_docker_image" {
  type        = string
  default     = ""
  description = "Docker image URI for the poller (defaults to gcr.io/{project}/dtkt-poller:latest)"
}

variable "dtkt_doppler_token" {
  type        = string
  sensitive   = true
  description = "Doppler service token for secrets injection"
}

variable "dtkt_pubsub_topic" {
  type        = string
  default     = "dtkt-mentions"
  description = "Pub/Sub topic name for detected mentions"
}

variable "dtkt_bucket_name" {
  type        = string
  default     = "dtkt-media"
  description = "GCS bucket name for downloaded media"
}

variable "dtkt_scanner_docker_image" {
  type        = string
  default     = ""
  description = "Docker image URI for the scanner (defaults to gcr.io/{project}/dtkt-scanner:latest)"
}

variable "dtkt_scanner_doppler_token" {
  type        = string
  sensitive   = true
  description = "Doppler service token for scanner secrets injection"
}

variable "dtkt_scanner_vm_machine_type" {
  type        = string
  default     = "e2-small"
  description = "Scanner VM machine type"
}

variable "dtkt_firestore_comments_collection" {
  type        = string
  default     = "dtkt-processed-comments"
  description = "Firestore collection for processed comment dedup"
}

variable "dtkt_firestore_circuit_collection" {
  type        = string
  default     = "dtkt-circuit-breaker"
  description = "Firestore collection for circuit breaker state"
}

variable "dtkt_firestore_circuit_doc" {
  type        = string
  default     = "dtkt-state"
  description = "Firestore document ID for circuit breaker state"
}

variable "dtkt_firestore_scans_collection" {
  type        = string
  default     = "dtkt-scans"
  description = "Firestore collection for scan results cache"
}

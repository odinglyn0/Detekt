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
  default     = "c2-standard-4"
  description = "Worker VM machine type"
}

variable "dtkt_vm_disk_size" {
  type        = number
  default     = 20
  description = "Boot disk size in GB"
}

variable "dtkt_worker_docker_image" {
  type        = string
  default     = ""
  description = "Docker image URI for the worker (defaults to gcr.io/{project}/dtkt-worker:latest)"
}

variable "dtkt_doppler_token" {
  type        = string
  sensitive   = true
  description = "Doppler service token for secrets injection"
}

variable "dtkt_bucket_name" {
  type        = string
  default     = "dtkt-media"
  description = "GCS bucket name for downloaded media"
}



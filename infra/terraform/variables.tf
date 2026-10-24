variable "project_id" {
  type        = string
  description = "GCP project that runs the refinery."
}

variable "region" {
  type        = string
  default     = "europe-west3" # Frankfurt: data stays in the EU
  description = "Region for buckets, Cloud SQL, Cloud Run and the crawler's egress address."
}

variable "name" {
  type        = string
  default     = "scr"
  description = "Prefix for every resource name."
}

variable "image" {
  type        = string
  description = "Container image (Artifact Registry) built from the repository's Dockerfile, pinned by digest."
  validation {
    condition     = can(regex("@sha256:[0-9a-f]{64}$", var.image))
    error_message = "Pin the image by digest (…@sha256:<64 hex>), so a job never runs code nobody reviewed."
  }
}

variable "worker_tasks" {
  type        = number
  default     = 20
  description = "Analysis tasks per run of the worker job. Each task leases jobs from PostgreSQL until none are due."
}

variable "worker_parallelism" {
  type        = number
  default     = 20
  description = "How many worker tasks run at once. Cloud SQL connections are the limit: keep it under max_connections / 2."
}

variable "worker_cpu" {
  type        = string
  default     = "2"
  description = "vCPUs per worker task. Matches config/pricing.yaml (cloud_run_job.vcpu), which the cost report assumes."
}

variable "worker_memory" {
  type        = string
  default     = "4Gi"
  description = "Memory per worker task (Whisper, CED and WeSpeaker together use about 1.5 GiB)."
}

variable "crawl_schedule" {
  type        = string
  default     = "0 2 * * *"
  description = "When the crawler runs (cron, in var.time_zone)."
}

variable "work_schedule" {
  type        = string
  default     = "30 * * * *"
  description = "When the analysis workers drain the queue (cron, in var.time_zone)."
}

variable "time_zone" {
  type    = string
  default = "Europe/Berlin"
}

variable "db_tier" {
  type        = string
  default     = "db-custom-2-7680"
  description = "Cloud SQL machine type."
}

variable "console_invokers" {
  type        = list(string)
  default     = []
  description = "Principals allowed to reach the API and review console (e.g. group:data-review@example.com). Empty: nobody outside the project."
}

variable "alert_email" {
  type        = string
  default     = ""
  description = "Where dead-letter and failed-run alerts go. Empty: no notification channel."
}

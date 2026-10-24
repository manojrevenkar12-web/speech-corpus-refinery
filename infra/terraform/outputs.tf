output "crawler_egress_ip" {
  value       = google_compute_address.crawler_egress.address
  description = "Publish this in docs/CRAWLER.md: every crawler request comes from it."
}

output "raw_bucket" {
  value = google_storage_bucket.raw.name
}

output "releases_bucket" {
  value = google_storage_bucket.releases.name
}

output "api_url" {
  value = google_cloud_run_v2_service.api.uri
}

output "image_repository" {
  value = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.images.repository_id}"
}

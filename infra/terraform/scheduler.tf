resource "google_cloud_scheduler_job" "run" {
  for_each = {
    crawl = { job = google_cloud_run_v2_job.crawl.name, schedule = var.crawl_schedule }
    work  = { job = google_cloud_run_v2_job.work.name, schedule = var.work_schedule }
  }
  name      = "${var.name}-${each.key}"
  region    = var.region
  schedule  = each.value.schedule
  time_zone = var.time_zone
  http_target {
    http_method = "POST"
    uri         = "https://run.googleapis.com/v2/projects/${var.project_id}/locations/${var.region}/jobs/${each.value.job}:run"
    oauth_token {
      service_account_email = google_service_account.sa["invoker"].email
      scope                 = "https://www.googleapis.com/auth/cloud-platform"
    }
  }
  retry_config {
    retry_count = 1
  }
  depends_on = [google_cloud_run_v2_job_iam_member.invoke]
}

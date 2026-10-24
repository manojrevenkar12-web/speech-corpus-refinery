resource "google_monitoring_notification_channel" "email" {
  count        = var.alert_email == "" ? 0 : 1
  display_name = "${var.name} data on-call"
  type         = "email"
  labels       = { email_address = var.alert_email }
}

# A failed crawl or worker run means files stop flowing; dead-lettered analysis jobs show up in
# the console's overview (jobs: analyse:dead) and in this alert's logs.
resource "google_monitoring_alert_policy" "job_failed" {
  display_name = "${var.name}: a refinery job failed"
  combiner     = "OR"
  conditions {
    display_name = "Cloud Run job execution failed"
    condition_threshold {
      filter          = "resource.type = \"cloud_run_job\" AND metric.type = \"run.googleapis.com/job/completed_execution_count\" AND metric.labels.result = \"failed\""
      comparison      = "COMPARISON_GT"
      threshold_value = 0
      duration        = "0s"
      aggregations {
        alignment_period   = "300s"
        per_series_aligner = "ALIGN_SUM"
      }
    }
  }
  notification_channels = [for c in google_monitoring_notification_channel.email : c.id]
  documentation {
    content   = "See docs/RUNBOOK.md: 'A job failed'."
    mime_type = "text/markdown"
  }
  depends_on = [google_project_service.this]
}

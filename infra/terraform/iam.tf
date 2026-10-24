# One service account per job, each with only what that job does. None has a project-level role.
locals {
  accounts = {
    crawler  = "Fetches robots.txt, TDMRep and audio; writes raw blobs"
    worker   = "Analyses audio; reads raw blobs"
    releaser = "Freezes releases; reads raw blobs, creates release objects"
    api      = "Review console and takedowns; reads blobs, deletes taken-down ones"
    invoker  = "Cloud Scheduler: starts the crawl and work jobs"
  }
}

resource "google_service_account" "sa" {
  for_each     = local.accounts
  account_id   = "${var.name}-${each.key}"
  display_name = "${var.name} ${each.key}"
  description  = each.value
}

# Everything that touches PostgreSQL reads the URL from Secret Manager.
resource "google_secret_manager_secret_iam_member" "db_url" {
  for_each  = toset(["crawler", "worker", "releaser", "api"])
  secret_id = google_secret_manager_secret.database_url.id
  role      = "roles/secretmanager.secretAccessor"
  member    = google_service_account.sa[each.key].member
}

resource "google_secret_manager_secret_iam_member" "api_keys" {
  secret_id = google_secret_manager_secret.api_keys.id
  role      = "roles/secretmanager.secretAccessor"
  member    = google_service_account.sa["api"].member
}

# Raw bucket. The crawler can create objects but not overwrite or delete them; only the API,
# which executes takedowns, can delete, through a custom role with exactly get and delete.
resource "google_storage_bucket_iam_member" "raw_create" {
  bucket = google_storage_bucket.raw.name
  role   = "roles/storage.objectCreator"
  member = google_service_account.sa["crawler"].member
}

resource "google_storage_bucket_iam_member" "raw_read" {
  for_each = toset(["crawler", "worker", "releaser", "api"])
  bucket   = google_storage_bucket.raw.name
  role     = "roles/storage.objectViewer"
  member   = google_service_account.sa[each.key].member
}

resource "google_project_iam_custom_role" "takedown_deleter" {
  role_id     = "${var.name}TakedownDeleter"
  title       = "Delete taken-down audio"
  description = "Lets the takedown flow remove a blob it has withdrawn."
  permissions = ["storage.objects.get", "storage.objects.delete"]
}

resource "google_storage_bucket_iam_member" "raw_delete" {
  bucket = google_storage_bucket.raw.name
  role   = google_project_iam_custom_role.takedown_deleter.id
  member = google_service_account.sa["api"].member
}

# Releases bucket: the release job creates, nobody overwrites; the API reads cards and summaries.
resource "google_storage_bucket_iam_member" "releases_create" {
  bucket = google_storage_bucket.releases.name
  role   = "roles/storage.objectCreator"
  member = google_service_account.sa["releaser"].member
}

resource "google_storage_bucket_iam_member" "releases_read" {
  bucket = google_storage_bucket.releases.name
  role   = "roles/storage.objectViewer"
  member = google_service_account.sa["api"].member
}

# The scheduler may start the two scheduled jobs and nothing else.
resource "google_cloud_run_v2_job_iam_member" "invoke" {
  for_each = { crawl = google_cloud_run_v2_job.crawl.name, work = google_cloud_run_v2_job.work.name }
  name     = each.value
  location = var.region
  role     = "roles/run.invoker"
  member   = google_service_account.sa["invoker"].member
}

resource "google_cloud_run_v2_service_iam_member" "console" {
  for_each = toset(var.console_invokers)
  name     = google_cloud_run_v2_service.api.name
  location = var.region
  role     = "roles/run.invoker"
  member   = each.value
}

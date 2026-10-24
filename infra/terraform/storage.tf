# Raw audio: content-addressed blobs (blobs/<sha[:2]>/<sha>). A takedown deletes the object, and
# deleted means deleted: soft delete is off, so withdrawn recordings are not kept for 7 days.
resource "google_storage_bucket" "raw" {
  name                        = "${var.project_id}-${var.name}-raw"
  location                    = var.region
  storage_class               = "STANDARD"
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  labels                      = local.labels
  soft_delete_policy {
    retention_duration_seconds = 0
  }
  lifecycle_rule {
    # blobs are read often in the first weeks (analysis, review, releases), rarely after
    condition {
      age = 90
    }
    action {
      type          = "SetStorageClass"
      storage_class = "NEARLINE"
    }
  }
  depends_on = [google_project_service.this]
}

# Releases are immutable: objects are created with if-generation-match=0 (store.publish_dir),
# and versioning keeps a copy of anything an operator deletes by mistake.
resource "google_storage_bucket" "releases" {
  name                        = "${var.project_id}-${var.name}-releases"
  location                    = var.region
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  labels                      = local.labels
  versioning {
    enabled = true
  }
  depends_on = [google_project_service.this]
}

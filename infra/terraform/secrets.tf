# The database URL and the API keys reach containers as Secret Manager references, never as
# plain environment values. The password is in Terraform state too: keep the state bucket private.
resource "google_secret_manager_secret" "database_url" {
  secret_id = "${var.name}-database-url"
  labels    = local.labels
  replication {
    user_managed {
      replicas {
        location = var.region
      }
    }
  }
  depends_on = [google_project_service.this]
}

resource "google_secret_manager_secret_version" "database_url" {
  secret      = google_secret_manager_secret.database_url.id
  secret_data = "postgresql://${google_sql_user.scr.name}:${random_password.db.result}@${google_sql_database_instance.pg.private_ip_address}:5432/${google_sql_database.scr.name}?sslmode=require"
}

# Keys are added by hand (`gcloud secrets versions add scr-api-keys`), as key:role pairs.
resource "google_secret_manager_secret" "api_keys" {
  secret_id = "${var.name}-api-keys"
  labels    = local.labels
  replication {
    user_managed {
      replicas {
        location = var.region
      }
    }
  }
  depends_on = [google_project_service.this]
}

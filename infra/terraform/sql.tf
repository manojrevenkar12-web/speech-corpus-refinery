# PostgreSQL is the record: frontier, job queue, decisions, releases, takedowns and the audit chain.
resource "google_sql_database_instance" "pg" {
  name                = "${var.name}-pg"
  database_version    = "POSTGRES_16"
  region              = var.region
  deletion_protection = true
  settings {
    tier              = var.db_tier
    availability_type = "REGIONAL"
    disk_autoresize   = true
    user_labels       = local.labels
    ip_configuration {
      ipv4_enabled    = false
      private_network = google_compute_network.vpc.id
      ssl_mode        = "ENCRYPTED_ONLY"
    }
    backup_configuration {
      enabled                        = true
      point_in_time_recovery_enabled = true
      start_time                     = "01:00"
      backup_retention_settings {
        retained_backups = 14
      }
    }
    database_flags {
      name  = "max_connections"
      value = "100"
    }
    insights_config {
      query_insights_enabled = true
    }
  }
  depends_on = [google_service_networking_connection.sql]
}

resource "google_sql_database" "scr" {
  name     = "scr"
  instance = google_sql_database_instance.pg.name
}

resource "random_password" "db" {
  length  = 32
  special = false
}

resource "google_sql_user" "scr" {
  name     = "scr"
  instance = google_sql_database_instance.pg.name
  password = random_password.db.result
}

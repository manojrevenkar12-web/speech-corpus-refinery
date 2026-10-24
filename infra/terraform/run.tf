locals {
  db_env = {
    name = "SCR_DATABASE_URL"
    secret = {
      secret  = google_secret_manager_secret.database_url.secret_id
      version = "latest"
    }
  }
}

# Same image everywhere; the job decides the command. All egress through the VPC, so the
# crawler's requests come from the NAT's static address and Cloud SQL is private.
resource "google_cloud_run_v2_job" "crawl" {
  name                = "${var.name}-crawl"
  location            = var.region
  deletion_protection = false
  labels              = local.labels
  template {
    task_count = 1
    template {
      service_account = google_service_account.sa["crawler"].email
      timeout         = "11400s"
      max_retries     = 1
      containers {
        image = var.image
        args  = ["crawl", "--workers", "8", "--deadline", "10800"]
        resources {
          limits = { cpu = "1", memory = "2Gi" }
        }
        env {
          name  = "SCR_GCS_BUCKET"
          value = google_storage_bucket.raw.name
        }
        env {
          name = local.db_env.name
          value_source {
            secret_key_ref {
              secret  = local.db_env.secret.secret
              version = local.db_env.secret.version
            }
          }
        }
      }
      vpc_access {
        egress = "ALL_TRAFFIC"
        network_interfaces {
          network    = google_compute_network.vpc.id
          subnetwork = google_compute_subnetwork.run.id
        }
      }
    }
  }
  depends_on = [google_compute_router_nat.egress, google_secret_manager_secret_version.database_url]
}

# Parallel analysis: every task leases jobs from PostgreSQL (FOR UPDATE SKIP LOCKED) until none
# are due, so tasks never share work and a task that dies loses its lease to another.
resource "google_cloud_run_v2_job" "work" {
  name                = "${var.name}-work"
  location            = var.region
  deletion_protection = false
  labels              = local.labels
  template {
    task_count  = var.worker_tasks
    parallelism = var.worker_parallelism
    template {
      service_account = google_service_account.sa["worker"].email
      timeout         = "3600s"
      max_retries     = 2
      containers {
        image = var.image
        args  = ["work", "--processes", var.worker_cpu]
        resources {
          limits = { cpu = var.worker_cpu, memory = var.worker_memory }
        }
        env {
          name  = "SCR_GCS_BUCKET"
          value = google_storage_bucket.raw.name
        }
        env {
          name = local.db_env.name
          value_source {
            secret_key_ref {
              secret  = local.db_env.secret.secret
              version = local.db_env.secret.version
            }
          }
        }
      }
      vpc_access {
        egress = "PRIVATE_RANGES_ONLY"
        network_interfaces {
          network    = google_compute_network.vpc.id
          subnetwork = google_compute_subnetwork.run.id
        }
      }
    }
  }
  depends_on = [google_secret_manager_secret_version.database_url]
}

# Run by hand: gcloud run jobs execute scr-release --args=release,v2
resource "google_cloud_run_v2_job" "release" {
  name                = "${var.name}-release"
  location            = var.region
  deletion_protection = false
  labels              = local.labels
  template {
    task_count = 1
    template {
      service_account = google_service_account.sa["releaser"].email
      timeout         = "21600s"
      max_retries     = 0
      containers {
        image = var.image
        args  = ["release", "--help"]
        resources {
          limits = { cpu = "4", memory = "8Gi" }
        }
        env {
          name  = "SCR_GCS_BUCKET"
          value = google_storage_bucket.raw.name
        }
        env {
          name  = "SCR_RELEASES_BUCKET"
          value = google_storage_bucket.releases.name
        }
        env {
          name = local.db_env.name
          value_source {
            secret_key_ref {
              secret  = local.db_env.secret.secret
              version = local.db_env.secret.version
            }
          }
        }
      }
      vpc_access {
        egress = "PRIVATE_RANGES_ONLY"
        network_interfaces {
          network    = google_compute_network.vpc.id
          subnetwork = google_compute_subnetwork.run.id
        }
      }
    }
  }
  depends_on = [google_secret_manager_secret_version.database_url]
}

# Run once after each deploy: schema migrations (advisory-locked) and the protected evaluation set.
resource "google_cloud_run_v2_job" "setup" {
  name                = "${var.name}-setup"
  location            = var.region
  deletion_protection = false
  labels              = local.labels
  template {
    task_count = 1
    template {
      service_account = google_service_account.sa["worker"].email
      timeout         = "900s"
      max_retries     = 1
      containers {
        image   = var.image
        command = ["sh", "-c"]
        args    = ["scr migrate && scr protect"]
        env {
          name = local.db_env.name
          value_source {
            secret_key_ref {
              secret  = local.db_env.secret.secret
              version = local.db_env.secret.version
            }
          }
        }
      }
      vpc_access {
        egress = "PRIVATE_RANGES_ONLY"
        network_interfaces {
          network    = google_compute_network.vpc.id
          subnetwork = google_compute_subnetwork.run.id
        }
      }
    }
  }
  depends_on = [google_secret_manager_secret_version.database_url]
}

# API and review console. Reachable only by var.console_invokers (Cloud Run IAM), and every
# request also needs an API key with the right role (viewer, reviewer, admin).
resource "google_cloud_run_v2_service" "api" {
  name                = "${var.name}-api"
  location            = var.region
  deletion_protection = false
  ingress             = "INGRESS_TRAFFIC_ALL"
  labels              = local.labels
  template {
    service_account = google_service_account.sa["api"].email
    scaling {
      min_instance_count = 0
      max_instance_count = 3
    }
    containers {
      image = var.image
      args  = ["serve", "--host", "0.0.0.0", "--port", "8080"]
      ports {
        container_port = 8080
      }
      resources {
        limits = { cpu = "1", memory = "1Gi" }
      }
      startup_probe {
        http_get {
          path = "/healthz"
        }
      }
      env {
        name  = "SCR_GCS_BUCKET"
        value = google_storage_bucket.raw.name
      }
      env {
        name  = "SCR_RELEASES_BUCKET"
        value = google_storage_bucket.releases.name
      }
      env {
        name = local.db_env.name
        value_source {
          secret_key_ref {
            secret  = local.db_env.secret.secret
            version = local.db_env.secret.version
          }
        }
      }
      env {
        name = "SCR_API_KEYS"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.api_keys.secret_id
            version = "latest"
          }
        }
      }
    }
    vpc_access {
      egress = "PRIVATE_RANGES_ONLY"
      network_interfaces {
        network    = google_compute_network.vpc.id
        subnetwork = google_compute_subnetwork.run.id
      }
    }
  }
  depends_on = [google_secret_manager_secret_version.database_url]
}

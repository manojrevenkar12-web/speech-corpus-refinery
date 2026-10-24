# One VPC. Jobs and the API use Direct VPC egress with ALL_TRAFFIC, so:
#  - Cloud SQL is reached on its private address only (no public IP);
#  - every request the crawler makes leaves through Cloud NAT from one static address, which
#    docs/CRAWLER.md publishes so site owners can recognise and, if they want, block us.

resource "google_compute_network" "vpc" {
  name                    = "${var.name}-vpc"
  auto_create_subnetworks = false
  depends_on              = [google_project_service.this]
}

resource "google_compute_subnetwork" "run" {
  name                     = "${var.name}-run"
  network                  = google_compute_network.vpc.id
  region                   = var.region
  ip_cidr_range            = "10.20.0.0/22"
  private_ip_google_access = true
}

resource "google_compute_global_address" "sql_range" {
  name          = "${var.name}-sql-range"
  purpose       = "VPC_PEERING"
  address_type  = "INTERNAL"
  prefix_length = 20
  network       = google_compute_network.vpc.id
}

resource "google_service_networking_connection" "sql" {
  network                 = google_compute_network.vpc.id
  service                 = "servicenetworking.googleapis.com"
  reserved_peering_ranges = [google_compute_global_address.sql_range.name]
}

resource "google_compute_address" "crawler_egress" {
  name         = "${var.name}-crawler-egress"
  region       = var.region
  address_type = "EXTERNAL"
  description  = "The crawler's published source address (docs/CRAWLER.md)."
}

resource "google_compute_router" "nat" {
  name    = "${var.name}-router"
  network = google_compute_network.vpc.id
  region  = var.region
}

resource "google_compute_router_nat" "egress" {
  name                               = "${var.name}-nat"
  router                             = google_compute_router.nat.name
  region                             = var.region
  nat_ip_allocate_option             = "MANUAL_ONLY"
  nat_ips                            = [google_compute_address.crawler_egress.self_link]
  source_subnetwork_ip_ranges_to_nat = "LIST_OF_SUBNETWORKS"
  subnetwork {
    name                    = google_compute_subnetwork.run.id
    source_ip_ranges_to_nat = ["ALL_IP_RANGES"]
  }
  log_config {
    enable = true
    filter = "ERRORS_ONLY"
  }
}

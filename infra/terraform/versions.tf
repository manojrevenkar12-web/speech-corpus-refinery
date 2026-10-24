terraform {
  required_version = ">= 1.6"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.10"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }
  # State lives in a bucket you create once by hand (it cannot hold itself):
  #   terraform init -backend-config="bucket=<project>-tfstate"
  backend "gcs" {
    prefix = "speech-corpus-refinery"
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

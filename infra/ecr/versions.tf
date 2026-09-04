terraform {
  # Same floor as infra/: the local toolchain is 1.15.2.
  required_version = ">= 1.15"

  required_providers {
    aws = {
      source = "hashicorp/aws"
      # Same pin as infra/ so both roots resolve the same provider build.
      version = "~> 6.63"
    }
  }
}

provider "aws" {
  region = var.region

  default_tags {
    tags = local.tags
  }
}

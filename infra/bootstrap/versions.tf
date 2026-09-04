terraform {
  # Same floor as infra/ and infra/ecr/: the local toolchain is 1.15.2.
  required_version = ">= 1.15"

  required_providers {
    aws = {
      source = "hashicorp/aws"
      # Same pin as the other two roots so all three resolve the same build.
      version = "~> 6.63"
    }
  }

  # No backend block on purpose. This root is what CREATES the state bucket the
  # other two roots use, so its own state has nowhere remote to live. It stays
  # local (terraform.tfstate, git-ignored) on the machine of whoever applies it,
  # once, by hand.
}

provider "aws" {
  region = var.region

  default_tags {
    tags = local.tags
  }
}

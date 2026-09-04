terraform {
  # Same floor as infra/: the local toolchain is 1.15.2.
  required_version = ">= 1.15"

  # Remote state in the S3 bucket infra/bootstrap/ creates. PARTIAL
  # configuration: `bucket` is deliberately absent and arrives at init time as
  # -backend-config="bucket=..." (backend.hcl.example, or the TF_STATE_BUCKET
  # repository variable in CI), because the bucket name is generated and this
  # repository does not carry it.
  #
  # use_lockfile is S3-native state locking, added in Terraform v1.10
  # (hashicorp/terraform#35661) and documented as "Whether to use a lockfile for
  # locking the state file. Defaults to `false`"
  # (https://developer.hashicorp.com/terraform/language/backend/s3). It replaces
  # the DynamoDB table: on the same page "DynamoDB-based locking is deprecated
  # and will be removed in a future minor version". Nothing else to create, and
  # nothing else to pay for.
  #
  # encrypt is "Enable server side encryption of the state and lock files"
  # (same page). The bucket also has SSE-S3 configured on its own side.
  # Same bucket as infra/, a different key: two roots, two independent states,
  # and this one is NOT destroyed at the end of a lab day.
  backend "s3" {
    key          = "ecr/terraform.tfstate"
    region       = "us-east-1"
    encrypt      = true
    use_lockfile = true
  }

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

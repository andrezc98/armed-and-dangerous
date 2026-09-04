terraform {
  # Local toolchain is 1.15.2; the EKS module only asks for >= 1.5.7.
  required_version = ">= 1.15"

  required_providers {
    aws = {
      source = "hashicorp/aws"
      # terraform-aws-modules/eks v21.25.0 requires >= 6.59 (versions.tf at the tag).
      version = "~> 6.63"
    }
    helm = {
      source = "hashicorp/helm"
      # v3 turned `kubernetes` and `exec` into attributes (`= {}`), not blocks.
      version = "~> 3.3"
    }
  }
}

provider "aws" {
  region = var.region

  default_tags {
    tags = local.tags
  }
}

# Talks to the cluster API to install the Karpenter chart. The token is fetched
# at apply time by the AWS CLI, so the apply must run with the sandbox profile.
provider "helm" {
  kubernetes = {
    host                   = module.eks.cluster_endpoint
    cluster_ca_certificate = base64decode(module.eks.cluster_certificate_authority_data)

    exec = {
      api_version = "client.authentication.k8s.io/v1beta1"
      command     = "aws"
      args        = ["eks", "get-token", "--cluster-name", module.eks.cluster_name]
    }
  }
}

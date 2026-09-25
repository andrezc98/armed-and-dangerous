variable "region" {
  description = "AWS region. m9g.4xlarge, m8i.4xlarge and m8a.4xlarge are all offered in us-east-1."
  type        = string
  default     = "us-east-1"
}

variable "cluster_name" {
  description = "EKS cluster name. Also the value of the karpenter.sh/discovery tag."
  type        = string
  default     = "aws-aad-eks-lab"

  validation {
    condition     = var.cluster_name == "aws-aad-eks-lab"
    error_message = "The karpenter.sh/discovery tag value is written out literally in infra/karpenter/ec2nodeclass-amd64.yaml and infra/karpenter/ec2nodeclass-arm64.yaml. Edit both files first, then relax this validation; otherwise Karpenter finds no subnet and no security group."
  }
}

variable "sandbox_account_id" {
  description = "The 12-digit sandbox account this lab may spend in. No default on purpose: the real value lives in the git-ignored terraform.tfvars and terraform_data.sandbox_account refuses to plan against any other account."
  type        = string

  validation {
    condition     = can(regex("^[0-9]{12}$", var.sandbox_account_id))
    error_message = "sandbox_account_id must be the 12 digits of an AWS account id."
  }
}

variable "admin_cidrs" {
  description = "CIDRs allowed to reach the public EKS API endpoint. On lab day this is the speaker's egress /32 and nothing else."
  type        = list(string)
}

variable "cluster_admin_principal_arns" {
  description = "IAM principals that get an EKS access entry with AmazonEKSClusterAdminPolicy on top of whoever ran the apply. Empty by default, which is the local path: there the human who applies IS the creator and enable_cluster_creator_admin_permissions already makes them admin. It stops being empty the moment the apply moves to GitHub Actions: then the creator is the CI role, and the laptop that runs kubectl and the runner all lab day is nobody. Every ARN carries the account id, so the value never lives in this repo - it arrives as TF_VAR_cluster_admin_principal_arns from the CLUSTER_ADMIN_ARNS repository variable."
  type        = list(string)
  default     = []

  validation {
    condition     = alltrue([for arn in var.cluster_admin_principal_arns : can(regex("^arn:aws[a-z-]*:iam::[0-9]{12}:(role|user)/", arn))])
    error_message = "Every entry must be an IAM role or user ARN (arn:aws:iam::<account>:role/... or :user/...)."
  }
}

variable "kubernetes_version" {
  description = "EKS control plane version. 1.36 is the newest in standard support and has a Bottlerocket aws-k8s-1.36 variant."
  type        = string
  default     = "1.36"
}

variable "vpc_cidr" {
  description = "CIDR of the VPC Terraform creates for the lab. It is torn down with everything else, so it only has to not collide with whatever the laptop is on."
  type        = string
  default     = "10.42.0.0/16"
}

variable "nodes_subnet_cidr" {
  description = "CIDR of the single public subnet that carries every node group and every Karpenter node. One AZ on purpose: same-AZ loader and SUT (Graviton perf runbook)."
  type        = string
  default     = "10.42.0.0/20"
}

variable "availability_zone" {
  description = "AZ of the node subnet. Must offer m8i.4xlarge, m8a.4xlarge, m9g.4xlarge, c7i.8xlarge and m7g.large."
  type        = string
  default     = "us-east-1a"
}

variable "control_plane_subnet_cidr" {
  description = "CIDR of the second public subnet. EKS demands subnets in at least two AZs for the control plane ENIs; no node ever lands here."
  type        = string
  default     = "10.42.16.0/27"
}

variable "control_plane_availability_zone" {
  description = "AZ of the control plane subnet. Any standard AZ other than var.availability_zone (Local Zones do not count)."
  type        = string
  default     = "us-east-1b"

  validation {
    condition     = var.control_plane_availability_zone != var.availability_zone
    error_message = "control_plane_availability_zone must differ from availability_zone (EKS requires control-plane subnets in two AZs)."
  }
}

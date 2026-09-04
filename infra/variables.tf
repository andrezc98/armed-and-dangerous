variable "region" {
  description = "AWS region. m9g.4xlarge and m8i.4xlarge are both offered in us-east-1."
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
  description = "AZ of the node subnet. Must offer m8i.4xlarge, m9g.4xlarge, c7i.4xlarge and m7g.large."
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
}

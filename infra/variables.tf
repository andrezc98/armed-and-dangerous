variable "region" {
  description = "AWS region. m9g.4xlarge and m8i.4xlarge are both offered in us-east-1."
  type        = string
  default     = "us-east-1"
}

variable "cluster_name" {
  description = "EKS cluster name. Also the value of the karpenter.sh/discovery tag."
  type        = string
  default     = "aws-aad-eks-lab"
}

variable "kubernetes_version" {
  description = "EKS control plane version. 1.36 is the newest in standard support and has a Bottlerocket aws-k8s-1.36 variant."
  type        = string
  default     = "1.36"
}

variable "vpc_id" {
  description = "Existing VPC to deploy into. No VPC, NAT or IGW is created; the real value lives in the git-ignored terraform.tfvars."
  type        = string
}

variable "subnet_cidr" {
  description = "CIDR of the single public subnet that carries every node group and every Karpenter node. One AZ on purpose: same-AZ loader and SUT (Graviton perf runbook)."
  type        = string
}

variable "availability_zone" {
  description = "AZ of the node subnet. Must offer m8i.4xlarge, m9g.4xlarge, c7i.4xlarge and m7g.large."
  type        = string
}

variable "control_plane_subnet_cidr" {
  description = "CIDR of the second subnet. EKS demands subnets in at least two AZs for the control plane ENIs; no node ever lands here."
  type        = string
}

variable "control_plane_availability_zone" {
  description = "AZ of the control plane subnet. Any standard AZ other than var.availability_zone (Local Zones do not count)."
  type        = string
}

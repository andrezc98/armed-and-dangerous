# Copy to terraform.tfvars (git-ignored) and fill in with real sandbox values.
# Nothing here is real: no account IDs, no VPC IDs, no ARNs.

# The account the apply is allowed to run in. Terraform compares it with
# aws_caller_identity and stops the plan if they differ, so a mistyped
# AWS_PROFILE cannot build the lab somewhere else. Replace with the real sandbox
# account id in terraform.tfvars; this placeholder is not an account.
sandbox_account_id = "000000000000"

# Public API endpoint allow list. Replace with the real egress /32 of the laptop
# that runs kubectl on lab day (curl https://checkip.amazonaws.com). This value
# is from the RFC 5737 documentation range and reaches nothing.
admin_cidrs = ["203.0.113.7/32"]

# Defaults, listed so the tfvars is a complete picture of the lab. Terraform
# creates this VPC and destroys it with the rest; there is no existing network
# to point at any more.
region             = "us-east-1"
cluster_name       = "aws-aad-eks-lab"
kubernetes_version = "1.36"

vpc_cidr = "10.42.0.0/16"

# Every node group and every Karpenter node lives in this one subnet/AZ.
nodes_subnet_cidr = "10.42.0.0/20"
availability_zone = "us-east-1a"

# Only the control plane ENIs; EKS demands a second AZ. A /27 is enough.
control_plane_subnet_cidr       = "10.42.16.0/27"
control_plane_availability_zone = "us-east-1b"

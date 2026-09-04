# Copy to terraform.tfvars (git-ignored) and fill in with real sandbox values.
# Nothing here is real: no account IDs, no VPC IDs, no ARNs.

vpc_id = "vpc-000000000000example"

# Every node group and every Karpenter node lives in this one subnet/AZ.
subnet_cidr       = "10.0.240.0/24"
availability_zone = "us-east-1a"

# Public API endpoint allow list. Replace with the real egress /32 of the laptop
# that runs kubectl on lab day (curl https://checkip.amazonaws.com). This value
# is from the RFC 5737 documentation range and reaches nothing.
admin_cidrs = ["203.0.113.7/32"]

# Only the control plane ENIs; EKS demands a second AZ. A /28 is enough.
control_plane_subnet_cidr       = "10.0.241.0/28"
control_plane_availability_zone = "us-east-1b"

# Defaults, listed so the tfvars is a complete picture of the lab.
region             = "us-east-1"
cluster_name       = "aws-aad-eks-lab"
kubernetes_version = "1.36"

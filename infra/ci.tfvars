# Values the CI run of this root needs and that are safe to commit: no account
# id, no ARN, no egress address. .github/workflows/infra.yml passes this file
# with -var-file=ci.tfvars.
#
# The two variables that are NOT here arrive as TF_VAR_* environment variables
# from GitHub *repository variables* (not secrets):
#   TF_VAR_sandbox_account_id           <- vars.SANDBOX_ACCOUNT_ID
#   TF_VAR_admin_cidrs                  <- vars.ADMIN_CIDRS   (HCL list, e.g. ["203.0.113.7/32"])
#   TF_VAR_cluster_admin_principal_arns <- vars.CLUSTER_ADMIN_ARNS (HCL list of IAM ARNs)
# An account id is not a secret, but it does not belong in a repository either;
# the egress /32 of the laptop changes on every lab day. Details in
# infra/bootstrap/README.md.

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

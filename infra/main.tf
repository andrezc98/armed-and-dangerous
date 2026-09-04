locals {
  tags = {
    Project     = "armed-and-dangerous"
    Environment = "lab"
    Owner       = "andres-zeballos"
    ManagedBy   = "terraform"
  }
}

################################################################################
# Network: existing VPC, own subnets and route table
################################################################################

# The sandbox VPC belongs to someone else: reuse its IGW, never touch its route
# tables. Everything created here is free (subnets + one route table).
data "aws_internet_gateway" "existing" {
  filter {
    name   = "attachment.vpc-id"
    values = [var.vpc_id]
  }
}

# Every node group and every Karpenter node lands here: one subnet, one AZ, so
# loader and SUT are always same-AZ. Public because the VPC has no NAT.
resource "aws_subnet" "nodes" {
  vpc_id                  = var.vpc_id
  cidr_block              = var.subnet_cidr
  availability_zone       = var.availability_zone
  map_public_ip_on_launch = true

  tags = {
    Name                     = "${var.cluster_name}-nodes"
    "karpenter.sh/discovery" = var.cluster_name
  }
}

# EKS requires "at least two subnets that are in different Availability Zones".
# This one exists only to satisfy that: it is passed as control_plane_subnet_ids
# and never as subnet_ids, so no node group and no EC2NodeClass can use it.
resource "aws_subnet" "control_plane" {
  vpc_id            = var.vpc_id
  cidr_block        = var.control_plane_subnet_cidr
  availability_zone = var.control_plane_availability_zone

  tags = {
    Name = "${var.cluster_name}-control-plane"
  }
}

resource "aws_route_table" "lab" {
  vpc_id = var.vpc_id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = data.aws_internet_gateway.existing.internet_gateway_id
  }

  tags = {
    Name = var.cluster_name
  }
}

resource "aws_route_table_association" "nodes" {
  subnet_id      = aws_subnet.nodes.id
  route_table_id = aws_route_table.lab.id
}

resource "aws_route_table_association" "control_plane" {
  subnet_id      = aws_subnet.control_plane.id
  route_table_id = aws_route_table.lab.id
}

################################################################################
# Bottlerocket version gate for the THP knob
################################################################################

# settings.kernel.hugepages.transparent landed in Bottlerocket 1.64.0
# ("Add support for static and transparent hugepages", release notes v1.64.0).
# If the published EKS-optimized AMI is older, userdata/thp.toml is a no-op and
# the tuned cells would silently measure the same thing as the stock cells.
data "aws_ssm_parameter" "bottlerocket_image_version" {
  for_each = toset(["x86_64", "arm64"])

  name = "/aws/service/bottlerocket/aws-k8s-${var.kubernetes_version}/${each.key}/latest/image_version"
}

locals {
  # image_version looks like "1.64.0-7c4f0d2b"; only the semver part matters.
  # insecure_value is the non-sensitive twin of value (public parameter).
  bottlerocket_version = {
    for arch, p in data.aws_ssm_parameter.bottlerocket_image_version :
    arch => split("-", p.insecure_value)[0]
  }

  # major*1e6 + minor*1e3 + patch, so a single >= comparison is enough.
  bottlerocket_weight = {
    for arch, v in local.bottlerocket_version :
    arch => sum([for i, part in split(".", v) : tonumber(part) * pow(1000, 2 - i)])
  }

  bottlerocket_thp_min_weight = 1 * pow(1000, 2) + 64 * pow(1000, 1) + 0
}

resource "terraform_data" "bottlerocket_supports_thp" {
  input = local.bottlerocket_version

  lifecycle {
    precondition {
      condition     = alltrue([for w in local.bottlerocket_weight : w >= local.bottlerocket_thp_min_weight])
      error_message = "Bottlerocket must be >= 1.64.0 for settings.kernel.hugepages.transparent; the published aws-k8s-${var.kubernetes_version} AMIs are ${jsonencode(local.bottlerocket_version)}. Switch infra/userdata/thp.toml to the settings.boot fallback documented inside that file."
    }
  }
}

################################################################################
# EBS CSI driver: IAM role assumed through EKS Pod Identity
################################################################################

# Without the driver no PVC binds (no in-tree provisioner since 1.23) and the
# MongoDB StatefulSet stays Pending. Same trap as the kcd cluster.
data "aws_iam_policy_document" "ebs_csi_assume_role" {
  statement {
    sid     = "AllowEksAuthToAssumeRoleForPodIdentity"
    actions = ["sts:AssumeRole", "sts:TagSession"]

    principals {
      type        = "Service"
      identifiers = ["pods.eks.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "ebs_csi" {
  name               = "aws-aad-ebs-csi"
  assume_role_policy = data.aws_iam_policy_document.ebs_csi_assume_role.json
}

resource "aws_iam_role_policy_attachment" "ebs_csi" {
  role = aws_iam_role.ebs_csi.name
  # V2 scopes the permissions to volumes tagged ebs.csi.aws.com/cluster, which
  # the driver applies itself to everything it provisions dynamically.
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonEBSCSIDriverPolicyV2"
}

################################################################################
# EKS cluster
################################################################################

module "eks" {
  source  = "terraform-aws-modules/eks/aws"
  version = "~> 21.25"

  name               = var.cluster_name
  kubernetes_version = var.kubernetes_version

  endpoint_public_access                   = true  # kubectl and the runner live on the Mac (default: false)
  authentication_mode                      = "API" # access entries; v21 dropped aws-auth
  enable_cluster_creator_admin_permissions = true  # without it you are not admin of your own cluster (default: false)

  addons = {
    coredns    = {}
    kube-proxy = {}
    vpc-cni    = { before_compute = true }
    # Pod Identity backs both the EBS CSI role below and Karpenter's controller.
    eks-pod-identity-agent = { before_compute = true }
    aws-ebs-csi-driver = {
      pod_identity_association = [{
        role_arn        = aws_iam_role.ebs_csi.arn
        service_account = "ebs-csi-controller-sa"
      }]
    }
    # Community add-on (owner "community"), no IAM of any kind. Feeds
    # `kubectl top`, the loader CPU guard and the CPU-per-Gbps number.
    metrics-server = {}
  }

  vpc_id                   = var.vpc_id
  subnet_ids               = [aws_subnet.nodes.id]
  control_plane_subnet_ids = [aws_subnet.nodes.id, aws_subnet.control_plane.id]

  eks_managed_node_groups = local.node_groups

  # Karpenter discovers the node security group by this tag; exactly one
  # security group in the account may carry it.
  node_security_group_tags = {
    "karpenter.sh/discovery" = var.cluster_name
  }

  tags = local.tags
}

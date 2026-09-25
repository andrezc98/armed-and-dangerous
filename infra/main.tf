locals {
  tags = {
    Project     = "armed-and-dangerous"
    Environment = "lab"
    Owner       = "andres-zeballos"
    ManagedBy   = "terraform"
  }
}

################################################################################
# Network: the lab's own VPC, two public subnets, no NAT
################################################################################

# The lab builds and destroys its whole network every lab day: nothing here
# depends on somebody else's VPC, and `terraform destroy` takes the network with
# it. No private subnets and no NAT gateway on purpose - every node has to pull
# images and reach the public EKS endpoint, and a NAT gateway is the most
# expensive thing this lab could leave running while nothing is measuring.
#
# The module creates the internet gateway, the public route table, its default
# route and the associations by itself: `create_igw` is "Controls if an Internet
# Gateway is created for public subnets and the related routes that connect
# them" and defaults to `true`
# (https://raw.githubusercontent.com/terraform-aws-modules/terraform-aws-vpc/v6.7.2/variables.tf).
module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "~> 6.7"

  name = "aws-aad-vpc"
  cidr = var.vpc_cidr

  # First AZ carries every node group and every Karpenter node, so loader and
  # SUT are always same-AZ; the second one exists only for the control plane
  # ENIs and never receives a node.
  azs            = [var.availability_zone, var.control_plane_availability_zone]
  public_subnets = [var.nodes_subnet_cidr, var.control_plane_subnet_cidr]

  # "Specify true to indicate that instances launched into the subnet should be
  # assigned a public IP address. Default is `false`" - with no NAT gateway this
  # is how a node reaches the internet at all.
  map_public_ip_on_launch = true

  # Both default to false in v6.7.2; written out because "no NAT" is a cost
  # decision of this lab and not an accident of the module's defaults.
  enable_nat_gateway = false
  single_nat_gateway = false

  enable_dns_hostnames = true
  enable_dns_support   = true

  # "Additional tags for the public subnets where the primary key is the AZ":
  # the module merges this into the tags of the subnet whose AZ matches the key,
  # so the Karpenter discovery tag lands on the nodes subnet and only there. A
  # plain `public_subnet_tags` would tag both, and Karpenter would be free to
  # put a node in the control plane subnet.
  public_subnet_tags_per_az = {
    (var.availability_zone) = {
      "karpenter.sh/discovery" = var.cluster_name
    }
  }

  # Project/Environment/Owner/ManagedBy arrive through the provider's
  # default_tags; passing `tags` here as well would only duplicate them.
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
# Sandbox gate: are these the credentials the lab is allowed to spend?
################################################################################

# The runner already refuses to run without an AWS_PROFILE whose name contains
# "sandbox" (runner/config.py require_sandbox), but a profile name is a string a
# human types. This is the technical half of the same rule: the account these
# credentials actually resolve to has to be the one written down in the
# git-ignored terraform.tfvars, or the plan stops before it creates a cluster in
# somebody else's account.
data "aws_caller_identity" "current" {}

resource "terraform_data" "sandbox_account" {
  input = var.sandbox_account_id

  lifecycle {
    precondition {
      condition     = data.aws_caller_identity.current.account_id == var.sandbox_account_id
      error_message = "These credentials belong to an account other than the sandbox_account_id in terraform.tfvars. Check which one is in use with `aws sts get-caller-identity` and export the sandbox AWS_PROFILE; do not widen this gate."
    }
  }
}

################################################################################
# Availability zone gate: does this AZ offer the five instance types at all?
################################################################################

locals {
  # Every instance type nodegroups.tf asks for. One AZ carries all of them or
  # the lab moves AZ (spec plan B), it never changes instance size.
  required_instance_types = ["m8i.4xlarge", "m8a.4xlarge", "m9g.4xlarge", "c7i.8xlarge", "m7g.large"]
}

# location_type turns the "location" filter into an AZ name: "Location type.
# Defaults to `region`. Valid values: `availability-zone`,
# `availability-zone-id`, and `region`" and "The `location` filter depends on
# the top-level `location_type` argument" (aws provider 6.63.0,
# website/docs/d/ec2_instance_type_offerings.html.markdown).
data "aws_ec2_instance_type_offerings" "nodes_az" {
  location_type = "availability-zone"

  filter {
    name   = "location"
    values = [var.availability_zone]
  }

  filter {
    name   = "instance-type"
    values = local.required_instance_types
  }
}

# Offering is not capacity: this only proves the AZ sells the type. Whether
# there is stock for it is answered on gate day, by the apply itself.
resource "terraform_data" "instance_types_offered_in_az" {
  input = sort(data.aws_ec2_instance_type_offerings.nodes_az.instance_types)

  lifecycle {
    precondition {
      condition     = length(setsubtract(local.required_instance_types, data.aws_ec2_instance_type_offerings.nodes_az.instance_types)) == 0
      error_message = "Availability zone ${var.availability_zone} does not offer ${jsonencode(setsubtract(local.required_instance_types, data.aws_ec2_instance_type_offerings.nodes_az.instance_types))}. Move the lab to an AZ that offers all of ${jsonencode(local.required_instance_types)}; do not change instance sizes."
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
  # Every write action is already scoped to resources the driver tags itself
  # (ebs.csi.aws.com/cluster, CSIVolumeName, kubernetes.io/created-for/pvc/name),
  # which is everything it provisions dynamically. ARN, type and version from
  # https://docs.aws.amazon.com/aws-managed-policy/latest/reference/AmazonEBSCSIDriverPolicyV2.html
  # (read 2026-09-04): "Type: AWS managed policy", "ARN:
  # arn:aws:iam::aws:policy/AmazonEBSCSIDriverPolicyV2", "Policy version: v1
  # (default)", created 2026-04-16 — NO service-role/ path segment.
  #
  # The 2026-09-04 apply died with NoSuchEntity on
  # arn:aws:iam::aws:policy/service-role/AmazonEBSCSIDriverPolicyV2: that ARN
  # spliced the service-role/ path of the older AmazonEBSCSIDriverPolicy onto
  # the V2 name, and named nothing that exists. The two real policies are
  # arn:aws:iam::aws:policy/service-role/AmazonEBSCSIDriverPolicy (v1 name, has
  # the path) and arn:aws:iam::aws:policy/AmazonEBSCSIDriverPolicyV2 (v2 name,
  # no path) — this uses the latter.
  policy_arn = "arn:aws:iam::aws:policy/AmazonEBSCSIDriverPolicyV2"
}

################################################################################
# EKS cluster
################################################################################

module "eks" {
  source  = "terraform-aws-modules/eks/aws"
  version = "~> 21.25"

  name               = var.cluster_name
  kubernetes_version = var.kubernetes_version

  # endpoint_public_access_cidrs defaults to ["0.0.0.0/0"] in the module ("List
  # of CIDR blocks which can access the Amazon EKS public API server endpoint",
  # terraform-aws-eks v21.25.0 variables.tf). The lab endpoint is for the
  # speaker's laptop and nothing else.
  endpoint_public_access                   = true # kubectl and the runner live on the Mac (default: false)
  endpoint_public_access_cidrs             = var.admin_cidrs
  authentication_mode                      = "API" # access entries; v21 dropped aws-auth
  enable_cluster_creator_admin_permissions = true  # without it you are not admin of your own cluster (default: false)

  # ...and the line above only covers the identity that ran the apply. When the
  # apply runs in GitHub Actions the creator is the CI role, so without this the
  # laptop that runs kubectl, the Karpenter CRDs and the runner all lab day gets
  # "error: You must be logged in to the server (Unauthorized)". Empty on the
  # local path, where the human is the creator.
  #
  # Policy ARN and scope from the EKS user guide, "Associate access policies with
  # access entries": arn:aws:eks::aws:cluster-access-policy/AmazonEKSClusterAdminPolicy,
  # and "If you want the IAM principal to have the permissions cluster-wide,
  # replace type=namespace,... with type=cluster".
  access_entries = {
    for arn in var.cluster_admin_principal_arns : basename(arn) => {
      principal_arn = arn
      policy_associations = {
        cluster_admin = {
          policy_arn   = "arn:aws:eks::aws:cluster-access-policy/AmazonEKSClusterAdminPolicy"
          access_scope = { type = "cluster" }
        }
      }
    }
  }

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
      # The provider's default_tags never reach a volume the CSI driver
      # provisions: Terraform does not create it, the driver's own CreateVolume
      # call does. Without this the end-of-day leak check
      # (`describe-volumes --filters Name=tag:Project,...`) comes back [] with a
      # 200Gi gp3 still billing. The add-on's configuration schema is the Helm
      # chart's values, where the key is controller.extraVolumeTags: "Extra
      # volume tags to attach to each dynamically provisioned volume"
      # (charts/aws-ebs-csi-driver/values.yaml, kubernetes-sigs/aws-ebs-csi-driver
      # master, read 2026-09-04; the same file has controller.extraCreateMetadata
      # default true, which is what also puts kubernetes.io/created-for/pvc/*
      # on the volume - the second filter of that leak check).
      configuration_values = jsonencode({
        controller = {
          extraVolumeTags = local.tags
        }
      })
    }
    # Community add-on (owner "community"), no IAM of any kind. Feeds
    # `kubectl top`, the loader CPU guard and the CPU-per-Gbps number.
    metrics-server = {}
  }

  vpc_id = module.vpc.vpc_id
  # Nodes only ever land in the first public subnet; the second is passed as a
  # control plane subnet and nowhere else.
  subnet_ids               = [module.vpc.public_subnets[0]]
  control_plane_subnet_ids = module.vpc.public_subnets

  eks_managed_node_groups = local.node_groups

  # The runner reads Java's pool gauges (actuator, 9966) and Go's cpuset control
  # (8080) through the API server's service proxy, and the module's recommended
  # rules only open 443, 10250 and the webhook ports from the control plane:
  # without these the proxy times out (calibration day 2026-09-24).
  node_security_group_additional_rules = {
    ingress_cluster_go = {
      description = "API server service proxy to the Go SUT (runner cpuset control)"
      from_port   = 8080, to_port = 8080, source_cluster_security_group = true
    }
    ingress_cluster_java = {
      description = "API server service proxy to the Java SUT actuator (runner pool gauges)"
      from_port   = 9966, to_port = 9966, source_cluster_security_group = true
    }
  }

  # Karpenter discovers the node security group by this tag; exactly one
  # security group in the account may carry it.
  node_security_group_tags = {
    "karpenter.sh/discovery" = var.cluster_name
  }

  tags = local.tags
}

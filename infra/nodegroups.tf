# One managed node group per cell (SPEC section 3). A cell is one silicon in one
# configuration; the runner scales its node group 0 -> 1 for the duration of the
# cell and back to 0, which is why desired_size is 0 here and owned by the AWS
# CLI afterwards (the module honours desired_size on create only).

locals {
  # Raw Bottlerocket TOML. With ami_type = BOTTLEROCKET_* and no custom AMI the
  # module ships bootstrap_extra_args as the whole user data and EKS merges it
  # over its own settings, so the files carry their own [settings.*] headers.
  #
  # base.toml is the CPU manager CONTROL and goes on all seven SUT cells; thp.toml
  # is a KNOB and only goes on the tuned ones. The two files declare disjoint
  # tables, so concatenating them is still one valid TOML document.
  base_user_data      = file("${path.module}/userdata/base.toml")
  thp_user_data       = file("${path.module}/userdata/thp.toml")
  tuned_sut_user_data = join("\n", [local.base_user_data, local.thp_user_data])

  sut_common = {
    use_name_prefix = false
    min_size        = 0
    desired_size    = 0
    # 2, not 1: the iperf3 cell needs a second node of the same type in the same
    # node group for the client side (SPEC section 4). Cost is unaffected, the
    # runner sets desiredSize.
    max_size = 2

    taints = {
      sut = {
        key   = "aad/sut"
        value = "true"
        # EKS API enum (NO_SCHEDULE), not the Kubernetes spelling NoSchedule.
        effect = "NO_SCHEDULE"
      }
    }
  }

  # Support node groups: min 0 so the cluster can idle between lab days
  # (speaker 2026-09-28). desired_size only counts on create; after that the
  # AWS CLI owns it: desiredSize=0 to park, =1 before a lab day.
  support_common = {
    use_name_prefix = false
    min_size        = 0
    max_size        = 1
    desired_size    = 1
  }

  node_group_defs = {
    # Bottlerocket as it ships: THP, C-states and SMT at their defaults. The
    # runbook reads those values off the node instead of assuming them. The one
    # thing stock does NOT mean is a floating cpuset: base.toml (static CPU
    # manager) is on every SUT cell, stock included, because CPU exclusivity is
    # the control that makes the cells comparable.
    "x86-stock" = merge(local.sut_common, {
      name                 = "aws-aad-mng-x86-stock"
      ami_type             = "BOTTLEROCKET_x86_64"
      instance_types       = ["m8i.4xlarge"]
      labels               = { "aad/cell" = "x86-stock" }
      bootstrap_extra_args = local.base_user_data
    })

    # THP always. C-states and network affinity are DaemonSets (Task 5).
    "x86-tuned" = merge(local.sut_common, {
      name                 = "aws-aad-mng-x86-tuned"
      ami_type             = "BOTTLEROCKET_x86_64"
      instance_types       = ["m8i.4xlarge"]
      labels               = { "aad/cell" = "x86-tuned" }
      bootstrap_extra_args = local.tuned_sut_user_data
    })

    # Everything x86-tuned has, plus SMT off: 8 real cores at the price of 16
    # vCPUs. EC2 requires both CPU options together; m8i.4xlarge is 8c x 2t by
    # default, so core_count stays at 8 and only threads_per_core changes.
    # No arm counterpart exists: Graviton cannot change threads per core.
    "x86-smtoff" = merge(local.sut_common, {
      name                 = "aws-aad-mng-x86-smtoff"
      ami_type             = "BOTTLEROCKET_x86_64"
      instance_types       = ["m8i.4xlarge"]
      labels               = { "aad/cell" = "x86-smtoff" }
      bootstrap_extra_args = local.tuned_sut_user_data
      cpu_options = {
        core_count       = 8
        threads_per_core = 1
      }
      max_size = 1 # not an iperf3 cell
    })

    # AMD column (speaker ruling 2026-09-25): m8a.4xlarge is AMD EPYC 9R45
    # (Turin), 16 vCPU = 16 physical cores, one thread per core, so it answers
    # "compare 16 real x86 cores with 16 Graviton cores". It mirrors x86-stock
    # and x86-tuned exactly; there is no SMT-off cell because there is no SMT.
    "amd-stock" = merge(local.sut_common, {
      name                 = "aws-aad-mng-amd-stock"
      ami_type             = "BOTTLEROCKET_x86_64"
      instance_types       = ["m8a.4xlarge"]
      labels               = { "aad/cell" = "amd-stock" }
      bootstrap_extra_args = local.base_user_data
    })

    "amd-tuned" = merge(local.sut_common, {
      name                 = "aws-aad-mng-amd-tuned"
      ami_type             = "BOTTLEROCKET_x86_64"
      instance_types       = ["m8a.4xlarge"]
      labels               = { "aad/cell" = "amd-tuned" }
      bootstrap_extra_args = local.tuned_sut_user_data
    })

    "arm-stock" = merge(local.sut_common, {
      name                 = "aws-aad-mng-arm-stock"
      ami_type             = "BOTTLEROCKET_ARM_64"
      instance_types       = ["m9g.4xlarge"]
      labels               = { "aad/cell" = "arm-stock" }
      bootstrap_extra_args = local.base_user_data
    })

    # THP always. There is no C-state or P-state knob on Graviton, and that
    # asymmetry is the point of the talk, not an omission.
    "arm-tuned" = merge(local.sut_common, {
      name                 = "aws-aad-mng-arm-tuned"
      ami_type             = "BOTTLEROCKET_ARM_64"
      instance_types       = ["m9g.4xlarge"]
      labels               = { "aad/cell" = "arm-tuned" }
      bootstrap_extra_args = local.tuned_sut_user_data
    })

    # k6, go-ycsb and the llama client. Untainted and x86 on purpose: go-ycsb is
    # built amd64 only. A loader over 70% CPU invalidates the run. c7i.4xlarge hit
    # 80% at 60k rps of k6 and 98% at 100k (gate); c7i.8xlarge read 71% with two
    # go-ycsb clients at 128 threads (calibration) -> c8i.16xlarge, 64 vCPU.
    "loader" = merge(local.support_common, {
      name           = "aws-aad-mng-loader"
      ami_type       = "BOTTLEROCKET_x86_64"
      instance_types = ["c8i.16xlarge"]
      labels         = { "aad/role" = "loader" }
    })

    # Pyroscope and the Karpenter controller. Nothing here touches a SUT.
    "tools" = merge(local.support_common, {
      name           = "aws-aad-mng-tools"
      ami_type       = "BOTTLEROCKET_ARM_64"
      instance_types = ["m7g.large"]
      labels         = { "aad/role" = "tools" }
    })
  }

  # For a Bottlerocket managed node group the releaseVersion EKS expects is the
  # very string the SSM image_version parameter returns ("1.64.0-<hash>"): the
  # module maps every BOTTLEROCKET_* ami_type to
  # "/aws/service/bottlerocket/aws-k8s-${local.ssm_kubernetes_version}/x86_64/latest/image_version"
  # and passes that value straight through as
  # "release_version = var.ami_id != \"\" ? null : var.use_latest_ami_release_version ? local.latest_ami_release_version : var.ami_release_version"
  # (terraform-aws-eks v21.25.0, modules/eks-managed-node-group/main.tf, lines
  # 415-416, 437 and 480). AWS's own docs never spell the format out.
  bottlerocket_ssm_arch = {
    BOTTLEROCKET_x86_64 = "x86_64"
    BOTTLEROCKET_ARM_64 = "arm64"
  }

  # Pin the AMI release from the same data source the THP gate reads, so the
  # image that boots is the image the gate checked and the exact release lands
  # in state. use_latest_ami_release_version defaults to true and wins over
  # ami_release_version (line 480 above), so it has to be turned off here.
  node_groups = {
    for cell, ng in local.node_group_defs : cell => merge(ng, {
      use_latest_ami_release_version = false
      ami_release_version            = data.aws_ssm_parameter.bottlerocket_image_version[local.bottlerocket_ssm_arch[ng.ami_type]].insecure_value
    })
  }
}

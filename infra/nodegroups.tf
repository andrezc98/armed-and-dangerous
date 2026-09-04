# One managed node group per cell (SPEC section 3). A cell is one silicon in one
# configuration; the runner scales its node group 0 -> 1 for the duration of the
# cell and back to 0, which is why desired_size is 0 here and owned by the AWS
# CLI afterwards (the module honours desired_size on create only).

locals {
  # Raw Bottlerocket TOML. With ami_type = BOTTLEROCKET_* and no custom AMI the
  # module ships bootstrap_extra_args as the whole user data and EKS merges it
  # over its own settings, so the file carries its own [settings.*] headers.
  thp_user_data = file("${path.module}/userdata/thp.toml")

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

  # Support node groups are always on while the cluster is up.
  support_common = {
    use_name_prefix = false
    min_size        = 1
    max_size        = 1
    desired_size    = 1
  }

  node_groups = {
    # Bottlerocket as it ships: THP, C-states and SMT at their defaults. The
    # runbook reads those values off the node instead of assuming them.
    "x86-stock" = merge(local.sut_common, {
      name           = "aws-aad-mng-x86-stock"
      ami_type       = "BOTTLEROCKET_x86_64"
      instance_types = ["m8i.4xlarge"]
      labels         = { "aad/cell" = "x86-stock" }
    })

    # THP always. C-states and network affinity are DaemonSets (Task 5).
    "x86-tuned" = merge(local.sut_common, {
      name                 = "aws-aad-mng-x86-tuned"
      ami_type             = "BOTTLEROCKET_x86_64"
      instance_types       = ["m8i.4xlarge"]
      labels               = { "aad/cell" = "x86-tuned" }
      bootstrap_extra_args = local.thp_user_data
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
      bootstrap_extra_args = local.thp_user_data
      cpu_options = {
        core_count       = 8
        threads_per_core = 1
      }
      max_size = 1 # not an iperf3 cell
    })

    "arm-stock" = merge(local.sut_common, {
      name           = "aws-aad-mng-arm-stock"
      ami_type       = "BOTTLEROCKET_ARM_64"
      instance_types = ["m9g.4xlarge"]
      labels         = { "aad/cell" = "arm-stock" }
    })

    # THP always. There is no C-state or P-state knob on Graviton, and that
    # asymmetry is the point of the talk, not an omission.
    "arm-tuned" = merge(local.sut_common, {
      name                 = "aws-aad-mng-arm-tuned"
      ami_type             = "BOTTLEROCKET_ARM_64"
      instance_types       = ["m9g.4xlarge"]
      labels               = { "aad/cell" = "arm-tuned" }
      bootstrap_extra_args = local.thp_user_data
    })

    # k6, go-ycsb and the llama client. Untainted and x86 on purpose: go-ycsb is
    # built amd64 only. A loader over 70% CPU invalidates the run.
    "loader" = merge(local.support_common, {
      name           = "aws-aad-mng-loader"
      ami_type       = "BOTTLEROCKET_x86_64"
      instance_types = ["c7i.4xlarge"]
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
}

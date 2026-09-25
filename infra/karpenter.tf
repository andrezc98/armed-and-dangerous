# Karpenter is not how the benchmark provisions nodes (that is nodegroups.tf).
# It exists for two slides: the generational arc (SPEC section 6, patch
# the instance-family requirement per generation) and the scale-from-zero clip.

module "karpenter" {
  source  = "terraform-aws-modules/eks/aws//modules/karpenter"
  version = "~> 21.25"

  cluster_name = module.eks.cluster_name

  # The name is hardcoded in infra/karpenter/ec2nodeclass-*.yaml, so it must not
  # get a random suffix.
  node_iam_role_use_name_prefix = false
  node_iam_role_name            = "aws-aad-karpenter-node"

  # create_pod_identity_association defaults to true and is the only identity
  # path in v21 (enable_v1_permissions and enable_irsa are gone). The controller
  # SSM permissions already cover /aws/service/*, which is what the
  # bottlerocket@latest alias resolves against.

  # "Determines whether the controller policy is created as a standard IAM
  # policy or inline IAM policy. This can be enabled when the error
  # `LimitExceeded: Cannot exceed quota for PolicySize: 6144` is received since
  # standard IAM policies have a limit of 6,144 characters versus an inline role
  # policy's limit of 10,240"
  # (modules/karpenter/variables.tf, terraform-aws-eks v21.25.0). That error is
  # exactly what the 2026-09-04 apply hit, and the managed-policy size quota
  # behind it (L-ED111B8C, "Managed policy length") is not adjustable, so there
  # is nothing to request an increase for: the controller policy has to be
  # inline on the role.
  enable_inline_policy = true

  # "Determines whether to enable native spot termination handling" (same file,
  # default true). Every node in this lab is on-demand - the seven cells, the
  # loader, the tools group and both arc NodePools all pin
  # karpenter.sh/capacity-type = on-demand - so the SQS queue, its policy and the
  # four EventBridge rules the module would create never see an event. Turning
  # it off deletes them, and it also drops the interruption statements from the
  # controller policy, which is the other half of why that policy no longer
  # overflows. settings.interruptionQueue disappears from the Helm values below
  # with it.
  enable_spot_termination = false

  tags = local.tags
}

# The chart itself is installed from the laptop, not by Terraform (see
# manifests/base/karpenter-values.yaml and manifests/base/README.md): CI's
# GitHub runner cannot reach the EKS API behind endpoint_public_access_cidrs
# (the speaker laptop's /32), so `helm_release` here failed apply with
# "Kubernetes cluster unreachable" (controller ruling, 2026-09-04, CI run
# 33927518231), and the same problem would break `destroy`. This module still
# creates everything the chart's ServiceAccount needs at apply time: the IAM
# role, the node IAM role, the pod identity association for SA `karpenter` in
# `kube-system`, and the access entry.

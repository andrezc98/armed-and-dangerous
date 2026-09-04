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
  # default true). Every node in this lab is on-demand - the five cells, the
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

# Anonymous pulls from public ECR are rate limited; the official example
# authenticates with a token, which is only issued in us-east-1.
data "aws_ecrpublic_authorization_token" "token" {
  region = "us-east-1"
}

resource "helm_release" "karpenter" {
  name      = "karpenter"
  namespace = "kube-system"

  repository          = "oci://public.ecr.aws/karpenter"
  repository_username = data.aws_ecrpublic_authorization_token.token.user_name
  repository_password = data.aws_ecrpublic_authorization_token.token.password
  chart               = "karpenter"
  version             = "1.14.1"

  # The chart's own affinity already keeps the controller off Karpenter nodes;
  # this pins it to the tools node group so it never shares a SUT.
  values = [
    <<-EOT
    # The tools node group is min = max = desired = 1 and the chart defaults to
    # "# -- Number of replicas." / "replicas: 2"
    # (charts/karpenter/values.yaml, aws/karpenter-provider-aws v1.14.1) with a
    # required hostname podAntiAffinity, so the second pod would sit
    # Unschedulable forever against a podDisruptionBudget of maxUnavailable: 1.
    replicas: 1
    nodeSelector:
      kubernetes.io/os: linux
      aad/role: tools
    dnsPolicy: Default
    settings:
      clusterName: ${module.eks.cluster_name}
      clusterEndpoint: ${module.eks.cluster_endpoint}
    # No settings.interruptionQueue on purpose, and no default to fall back on:
    # "Interruption queue is the name of the SQS queue used for processing
    # interruption events from EC2. Interruption handling is disabled if not
    # specified." / `interruptionQueue: ""` (charts/karpenter/values.yaml,
    # aws/karpenter-provider-aws v1.14.1), and the Deployment template only emits
    # the INTERRUPTION_QUEUE env var inside `{{- with .Values.settings.interruptionQueue }}`
    # (charts/karpenter/templates/deployment.yaml, same tag), so an absent value
    # is a supported configuration and not a rendering error. There is no queue
    # any more: enable_spot_termination = false above.
    EOT
  ]

  # The NodePool and EC2NodeClasses are plain YAML under infra/karpenter/,
  # applied with kubectl after this release: their CRDs do not exist at plan
  # time on a fresh cluster.
  wait = false
}

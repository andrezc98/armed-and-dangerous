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
      interruptionQueue: ${module.karpenter.queue_name}
    EOT
  ]

  # The NodePool and EC2NodeClasses are plain YAML under infra/karpenter/,
  # applied with kubectl after this release: their CRDs do not exist at plan
  # time on a fresh cluster.
  wait = false
}

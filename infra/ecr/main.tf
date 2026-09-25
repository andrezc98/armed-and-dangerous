locals {
  tags = {
    Project     = "armed-and-dangerous"
    Environment = "lab"
    Owner       = "andres-zeballos"
    ManagedBy   = "terraform"
  }

  # The four images apps/build-multiarch.sh builds. One repository each: ECR has
  # no namespaces, the repository name is the whole path after the registry, so
  # "aad-java" is what becomes <account>.dkr.ecr.<region>.amazonaws.com/aad-java.
  # aad-llama: llama.cpp server built with Arm KleidiAI for arm64 only
  # (apps/llama/build-kleidiai.sh), added on calibration day 2026-09-24.
  repositories = ["aad-java", "aad-go", "aad-iperf3", "aad-ycsb", "aad-llama"]
}

################################################################################
# Sandbox gate: are these the credentials the lab is allowed to spend?
################################################################################

# Same gate as infra/main.tf, for the same reason: a profile name is a string a
# human types, and this root creates resources that outlive the cluster. The
# account these credentials actually resolve to has to be the one written down
# in the git-ignored terraform.tfvars.
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
# One private repository per own image
################################################################################

# Docs (registry.terraform.io/providers/hashicorp/aws 6.63.0, r/ecr_repository):
#   image_tag_mutability - "The tag mutability setting for the repository. Must
#     be one of: MUTABLE, IMMUTABLE, IMMUTABLE_WITH_EXCLUSION, or
#     MUTABLE_WITH_EXCLUSION. Defaults to MUTABLE."
#   image_scanning_configuration.scan_on_push - "Indicates whether images are
#     scanned after being pushed to the repository (true) or not scanned
#     (false)."
#
# IMMUTABLE is the measurement control, not a security preference: the tag is
# the push date and it is what results/images.json hands the runner. A tag that
# can be moved means two lab days render the same manifest and pull two
# different binaries, and the second day's numbers are not comparable with the
# first day's.
resource "aws_ecr_repository" "own" {
  for_each = toset(local.repositories)

  name                 = each.key
  image_tag_mutability = "IMMUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }
}

# Docs (same provider, r/ecr_lifecycle_policy): `repository` is the "Name of the
# repository to apply the policy" and `policy` is "The policy document. This is
# a JSON formatted string."
#
# Rule shape from the ECR user guide (lifecycle_policy_parameters):
#   tagStatus - "Acceptable options are tagged, untagged, or any. [...] If you
#     specify tagged, then you must also specify a tagPrefixList value or a
#     tagPatternList value."
#   tagPatternList - "When creating a lifecycle policy for tagged images, it's
#     best practice to use a tagPatternList to specify the tags to expire."
#   countType imageCountMoreThan - "images are sorted from youngest to oldest
#     based on pushed_at_time and then all images greater than the specified
#     count are expired or archived."
#
# "*" as the only pattern is every tag: the lab tags by date, there is no
# release channel to distinguish. Five is a handful of lab days of history,
# enough to re-render an old results/ directory and still bounded.
#
# ponytail: one rule. No untagged rule because IMMUTABLE tags mean a re-push of
# the same tag is refused rather than orphaning the old manifest; add one if
# untagged manifests ever show up in `aws ecr list-images`.
resource "aws_ecr_lifecycle_policy" "own" {
  for_each = aws_ecr_repository.own

  repository = each.value.name

  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Keep the last 5 tagged images"
      selection = {
        tagStatus      = "tagged"
        tagPatternList = ["*"]
        countType      = "imageCountMoreThan"
        countNumber    = 5
      }
      action = {
        type = "expire"
      }
    }]
  })
}

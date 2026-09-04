locals {
  tags = {
    Project     = "armed-and-dangerous"
    Environment = "lab"
    Owner       = "andres-zeballos"
    ManagedBy   = "terraform"
  }
}

################################################################################
# Sandbox gate: are these the credentials the lab is allowed to spend?
################################################################################

# Same gate as infra/main.tf and infra/ecr/main.tf. This root hands out an
# AdministratorAccess role, so it is the last one that should run anywhere else.
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
# Remote state bucket for infra/ and infra/ecr/
################################################################################

# bucket_prefix, not a hand-written name: "Creates a unique bucket name
# beginning with the specified prefix" (aws provider 6.63.0, r/s3_bucket), and
# the suffix it appends is random, so the committed configuration never has to
# carry the real bucket name - which, like the account id, is not a secret but
# is not something this repo publishes either. The generated name is what the
# `state_bucket` output prints and what -backend-config="bucket=..." then feeds
# the other two roots.
#
# force_destroy stays at its default: "(Optional, Default:`false`) Boolean that
# indicates all objects [...] should be deleted from the bucket *when the bucket
# is destroyed*". This bucket holds the only copy of the lab's state. Emptying
# it as a side effect of a `terraform destroy` in the wrong directory is exactly
# the accident worth making impossible.
resource "aws_s3_bucket" "tfstate" {
  bucket_prefix = "aws-aad-tfstate-"
}

# Versioning is what turns a corrupted or truncated state push into something
# recoverable, and Terraform's own S3 backend documentation asks for it.
resource "aws_s3_bucket_versioning" "tfstate" {
  bucket = aws_s3_bucket.tfstate.id

  versioning_configuration {
    status = "Enabled"
  }
}

# SSE-S3. Written out rather than left to the account default: the state files
# of this lab carry the account id, every subnet id and every role ARN, and
# "encrypt = true" on the backend side only asks S3 to encrypt, it does not
# configure the bucket. AES256 is the SSE-S3 value ("Valid values are `AES256`,
# `aws:kms`, and `aws:kms:dsse`"); no KMS key, so no per-request key cost and no
# key policy to keep in sync with the GitHub Actions role.
resource "aws_s3_bucket_server_side_encryption_configuration" "tfstate" {
  bucket = aws_s3_bucket.tfstate.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# All four block settings on. New buckets get this by default today; it is
# written out because "the state bucket is never public" is a decision of this
# lab and not something to inherit silently.
resource "aws_s3_bucket_public_access_block" "tfstate" {
  bucket = aws_s3_bucket.tfstate.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Keep noncurrent versions 30 days. Two things pile up in a versioned state
# bucket: the previous state after every apply, and the `<key>.tflock` object
# that S3-native locking writes and deletes on every single command, each delete
# leaving a noncurrent version behind. An empty `filter {}` is the whole bucket.
resource "aws_s3_bucket_lifecycle_configuration" "tfstate" {
  # "Must have bucket versioning enabled first" (provider example).
  depends_on = [aws_s3_bucket_versioning.tfstate]

  bucket = aws_s3_bucket.tfstate.id

  rule {
    id     = "expire-noncurrent-state-versions"
    status = "Enabled"

    filter {}

    noncurrent_version_expiration {
      noncurrent_days = 30
    }
  }
}

################################################################################
# GitHub Actions OIDC: identity provider + the role the workflows assume
################################################################################

# No thumbprint_list. "(Optional) [...] For certain OIDC identity providers
# (e.g., Auth0, GitHub, GitLab, Google, or those using an Amazon S3-hosted JWKS
# endpoint), AWS relies on its own library of trusted root certificate
# authorities (CAs) for validation instead of using any configured thumbprints.
# In these cases, any configured `thumbprint_list` is retained in the
# configuration but not used for verification" (aws provider, r/
# iam_openid_connect_provider). IAM says the same from the other side: "AWS
# secures communication with OIDC identity providers (IdPs) using our library of
# trusted root certificate authorities (CAs) to verify the JSON Web Key Set
# (JWKS) endpoint's TLS certificate. If your OIDC IdP relies on a certificate
# that is not signed by one of these trusted CAs, only then we secure
# communication using the thumbprints set in the IdP's configuration"
# (https://docs.aws.amazon.com/IAM/latest/UserGuide/id_roles_providers_create_oidc.html).
# So a pinned thumbprint here would be a value nobody reads that still rots.
# The argument is omitted entirely rather than set to []: an empty list is not
# the same as "absent" on the IAM side.
#
# URL and audience are the two GitHub documents verbatim: "For the provider URL:
# Use `https://token.actions.githubusercontent.com`" and "For the 'Audience':
# Use `sts.amazonaws.com` if you are using the official action"
# (https://docs.github.com/en/actions/how-tos/secure-your-work/security-harden-deployments/oidc-in-aws).
resource "aws_iam_openid_connect_provider" "github" {
  url            = "https://token.actions.githubusercontent.com"
  client_id_list = ["sts.amazonaws.com"]
}

# StringEquals on both aud and sub, no wildcard: this role may be assumed by one
# repository, from one environment, and by nothing else. GitHub's own note:
# "AWS Identity and Access Management (IAM) recommends that users evaluate the
# IAM condition key, `token.actions.githubusercontent.com:sub`, in the trust
# policy of any role that trusts GitHub's OIDC identity provider (IdP)."
data "aws_iam_policy_document" "gha_assume_role" {
  statement {
    sid     = "AllowGitHubActionsToAssumeRole"
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.github.arn]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:sub"
      values   = [var.github_sub]
    }
  }
}

resource "aws_iam_role" "gha" {
  name               = "aws-aad-gha"
  description        = "Assumed by the GitHub Actions workflows of armed-and-dangerous through OIDC. Sandbox lab account only."
  assume_role_policy = data.aws_iam_policy_document.gha_assume_role.json
}

# AdministratorAccess, deliberately. This role builds and destroys a whole EKS
# cluster with its VPC, its IAM roles, its EKS access entries, its add-ons and
# its Karpenter submodule, plus four ECR repositories, in a personal sandbox
# account that holds nothing else. Writing the least-privilege policy for that
# surface is a project of its own and it would be re-derived on every module
# bump; the blast radius is already the whole sandbox account, and the gate that
# matters is the trust policy above (one repo, one environment) plus the
# terraform_data.sandbox_account precondition inside the two roots. Do not copy
# this root into an account that holds anything real without replacing it.
#
# ponytail: one managed policy. Narrow it when this stops being a throwaway
# sandbox, not before.
resource "aws_iam_role_policy_attachment" "gha_admin" {
  role       = aws_iam_role.gha.name
  policy_arn = "arn:aws:iam::aws:policy/AdministratorAccess"
}

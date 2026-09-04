variable "region" {
  description = "AWS region. Must be the region of the other two roots: the S3 backend of infra/ and infra/ecr/ points at this bucket with region = us-east-1 written out."
  type        = string
  default     = "us-east-1"
}

variable "sandbox_account_id" {
  description = "The 12-digit sandbox account this bootstrap may create resources in. No default on purpose: the real value lives in the git-ignored terraform.tfvars and terraform_data.sandbox_account refuses to plan against any other account."
  type        = string

  validation {
    condition     = can(regex("^[0-9]{12}$", var.sandbox_account_id))
    error_message = "sandbox_account_id must be the 12 digits of an AWS account id."
  }
}

variable "github_sub" {
  description = <<-EOT
    The exact `sub` claim the GitHub Actions OIDC token carries, matched with
    StringEquals in the role trust policy. One workflow environment, one value.

    Default is the classic form documented in "Configuring OpenID Connect in
    Amazon Web Services": `repo:ORG-NAME/REPO-NAME:environment:ENVIRONMENT-NAME`.

    CHECK THIS BEFORE THE APPLY. "For repositories created after July 15, 2026,
    or that have opted in to immutable subject claims, the `sub` claim includes
    immutable owner and repository IDs" and then looks like
    `repo:OWNER@OWNER-ID/REPO@REPO-ID:environment:lab`
    (https://docs.github.com/en/actions/reference/security/oidc). If this
    repository is one of those, the default below never matches and every job
    fails on AssumeRoleWithWebIdentity; set the immutable form here instead.
  EOT
  type        = string
  default     = "repo:andrezc98/armed-and-dangerous:environment:lab"

  validation {
    condition     = startswith(var.github_sub, "repo:")
    error_message = "github_sub is a GitHub OIDC subject claim and always starts with \"repo:\"."
  }
}

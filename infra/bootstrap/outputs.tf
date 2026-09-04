# Both values go straight into GitHub *variables* (not secrets) with
# `gh variable set`; infra/bootstrap/README.md has the two commands. Neither is
# committed: the bucket name is random and the role ARN carries the account id.

output "state_bucket" {
  description = "Name of the S3 bucket holding the state of infra/ and infra/ecr/. Feed it to both roots as -backend-config=\"bucket=<this>\" and to CI as the TF_STATE_BUCKET repository variable."
  value       = aws_s3_bucket.tfstate.id
}

output "gha_role_arn" {
  description = "ARN of the role the GitHub Actions workflows assume through OIDC. Goes into CI as the AWS_ROLE_ARN repository variable. Carries the account id, so it never gets committed."
  value       = aws_iam_role.gha.arn
}

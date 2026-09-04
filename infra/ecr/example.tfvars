# Copy to terraform.tfvars (git-ignored) and fill in with the real sandbox
# values. Nothing here is real: no account IDs.

# The account the apply is allowed to run in. Terraform compares it with
# aws_caller_identity and stops the plan if they differ, so a mistyped
# AWS_PROFILE cannot create the repositories somewhere else. Replace with the
# real sandbox account id in terraform.tfvars; this placeholder is not an
# account.
sandbox_account_id = "000000000000"

# Default, listed so the tfvars is a complete picture. Has to be the region of
# the cluster in infra/.
region = "us-east-1"

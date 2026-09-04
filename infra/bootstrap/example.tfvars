# Copy to terraform.tfvars (git-ignored) and fill in with the real sandbox
# values. Nothing here is real: no account IDs.

# The account this bootstrap is allowed to create resources in. Terraform
# compares it with aws_caller_identity and stops the plan if they differ, so a
# mistyped AWS_PROFILE cannot leave an AdministratorAccess role in somebody
# else's account. Replace with the real sandbox account id in terraform.tfvars;
# this placeholder is not an account.
sandbox_account_id = "000000000000"

# Default, listed so the tfvars is a complete picture. Has to be the region
# written into the backend blocks of infra/ and infra/ecr/.
region = "us-east-1"

# The sub claim of the OIDC token, matched with StringEquals. Uncomment and
# adjust ONLY if the repository uses immutable subject claims (created after
# 2026-07-15 or opted in), where the form is
# repo:OWNER@OWNER-ID/REPO@REPO-ID:environment:lab. See the variable's
# description in variables.tf.
# github_sub = "repo:andrezc98/armed-and-dangerous:environment:lab"

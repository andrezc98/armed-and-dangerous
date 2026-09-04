# Values the CI run of this root needs and that are safe to commit.
# .github/workflows/infra.yml passes this file with -var-file=ci.tfvars.
#
# sandbox_account_id is not here: it arrives as TF_VAR_sandbox_account_id from
# the SANDBOX_ACCOUNT_ID GitHub repository variable.

region = "us-east-1"

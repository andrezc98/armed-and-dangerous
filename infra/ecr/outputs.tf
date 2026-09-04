# Both outputs carry the account id, which is why the file they are redirected
# into (results/<date>/ecr.json) is git-ignored.

output "registry" {
  description = "Registry host the runner prefixes every own image with. The form is the one the ECR user guide uses for docker login: <aws_account_id>.dkr.ecr.<region>.amazonaws.com."
  value       = "${data.aws_caller_identity.current.account_id}.dkr.ecr.${var.region}.amazonaws.com"
}

output "repository_urls" {
  description = "Image name to repository URL, straight from the provider (repository_url is \"The URL of the repository (in the form aws_account_id.dkr.ecr.region.amazonaws.com/repositoryName)\")."
  value       = { for name, repo in aws_ecr_repository.own : name => repo.repository_url }
}

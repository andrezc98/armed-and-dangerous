variable "region" {
  description = "AWS region. Must be the region of the cluster in infra/: nodes pull from the regional ECR endpoint and a cross-region pull is billed as data transfer."
  type        = string
  default     = "us-east-1"
}

variable "sandbox_account_id" {
  description = "The 12-digit sandbox account these repositories belong to. No default on purpose: the real value lives in the git-ignored terraform.tfvars and terraform_data.sandbox_account refuses to plan against any other account."
  type        = string

  validation {
    condition     = can(regex("^[0-9]{12}$", var.sandbox_account_id))
    error_message = "sandbox_account_id must be the 12 digits of an AWS account id."
  }
}

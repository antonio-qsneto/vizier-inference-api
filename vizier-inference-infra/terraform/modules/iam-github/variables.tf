variable "github_repo" {
  description = "GitHub repository in org/repo format"
  type        = string
}

variable "github_branch" {
  description = "GitHub branch allowed to assume role"
  type        = string
  default     = "main"
}

variable "aws_region" {
  type = string
}

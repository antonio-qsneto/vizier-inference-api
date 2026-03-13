variable "github_repo" {
  description = "GitHub repository in org/repo format"
  type        = string
}

variable "github_branch" {
  description = "GitHub branch allowed to assume role"
  type        = string
  default     = "main"
}

variable "github_environments" {
  description = "Optional GitHub environments allowed to assume this role"
  type        = list(string)
  default     = []
}

variable "aws_region" {
  type = string
}

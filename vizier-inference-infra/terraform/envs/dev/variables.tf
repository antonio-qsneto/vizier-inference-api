variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "availability_zone" {
  type    = string
  default = "us-east-1a"
}

variable "vpc_cidr" {
  type    = string
  default = "10.0.0.0/16"
}

variable "api_image" {
  type        = string
  description = "ECR image URI for the FastAPI container"
}

variable "worker_image" {
  type        = string
  description = "ECR image URI for the GPU worker container"
}

variable "biomedparse_image" {
  type        = string
  description = "ECR image URI for the BiomedParse model container"
}

variable "project_name" {
  type        = string
  description = "Project name used for resource naming"
  default     = "vizier-inference"
}

variable "environment" {
  type        = string
  description = "Environment name used for resource naming"
  default     = "dev"
}

variable "cognito_callback_urls" {
  type        = list(string)
  description = "Callback URLs for Cognito Hosted UI OAuth"
  default = [
    "https://oauth.pstmn.io/v1/callback",
    "http://localhost:8000/auth/callback",
  ]
}

variable "cognito_logout_urls" {
  type        = list(string)
  description = "Logout URLs for Cognito Hosted UI OAuth"
  default = [
    "http://localhost:8000/",
  ]
}

variable "cognito_mfa_configuration" {
  type        = string
  description = "MFA setting for Cognito user pool: OFF, OPTIONAL, ON"
  default     = "OFF"

  validation {
    condition     = contains(["OFF", "OPTIONAL", "ON"], var.cognito_mfa_configuration)
    error_message = "cognito_mfa_configuration must be one of: OFF, OPTIONAL, ON."
  }
}

variable "cognito_ses_source_arn" {
  type        = string
  description = "Optional SES identity ARN for Cognito developer email sending"
  default     = null
}

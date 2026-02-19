variable "project_name" {
  type        = string
  description = "Project name used in Cognito resource naming"
}

variable "environment" {
  type        = string
  description = "Environment name used in Cognito resource naming"
}

variable "callback_urls" {
  type        = list(string)
  description = "OAuth callback URLs for Cognito Hosted UI client"
  default = [
    "https://oauth.pstmn.io/v1/callback",
    "http://localhost:8000/auth/callback",
  ]
}

variable "logout_urls" {
  type        = list(string)
  description = "OAuth logout URLs for Cognito Hosted UI client"
  default = [
    "http://localhost:8000/",
  ]
}

variable "mfa_configuration" {
  type        = string
  description = "MFA setting for user pool: OFF, OPTIONAL, or ON"
  default     = "OFF"

  validation {
    condition     = contains(["OFF", "OPTIONAL", "ON"], var.mfa_configuration)
    error_message = "mfa_configuration must be one of: OFF, OPTIONAL, ON."
  }
}

variable "ses_source_arn" {
  type        = string
  description = "Optional SES identity ARN for Cognito email sending"
  default     = null
}

variable "tags" {
  type        = map(string)
  description = "Tags to apply to Cognito resources"
  default     = {}
}

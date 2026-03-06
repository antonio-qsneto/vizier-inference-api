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

variable "gpu_ami_id" {
  type        = string
  description = "Baked ECS GPU AMI used by g4dn worker nodes"
  default     = "ami-0b2483db0c00858b5"
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

variable "jobs_table_name" {
  type        = string
  description = "DynamoDB table name for inference job status"
  default     = "vizier-inference-jobs-dev"
}

variable "jobs_queue_name" {
  type        = string
  description = "SQS queue name for inference jobs"
  default     = "vizier-inference-jobs-dev"
}

variable "jobs_dlq_name" {
  type        = string
  description = "SQS dead-letter queue name for failed inference jobs"
  default     = "vizier-inference-jobs-dev-dlq"
}

variable "s3_artifacts_bucket_name" {
  type        = string
  description = "Optional S3 bucket name for artifacts; if null, a deterministic name is generated"
  default     = null
}

variable "job_artifacts_prefix" {
  type        = string
  description = "Prefix used for per-job artifacts inside the S3 bucket"
  default     = "jobs"
}

variable "s3_kms_key_arn" {
  type        = string
  description = "Optional KMS key ARN for S3 bucket SSE-KMS encryption"
  default     = null
}

variable "dynamodb_kms_key_arn" {
  type        = string
  description = "Optional KMS key ARN for DynamoDB table encryption"
  default     = null
}

variable "cognito_callback_urls" {
  type        = list(string)
  description = "Callback URLs for Cognito Hosted UI OAuth"
  default = [
    "https://oauth.pstmn.io/v1/callback",
    "http://localhost:3000/auth/callback",
    "http://localhost:8000/auth/callback",
  ]
}

variable "cognito_logout_urls" {
  type        = list(string)
  description = "Logout URLs for Cognito Hosted UI OAuth"
  default = [
    "http://localhost:3000/login",
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

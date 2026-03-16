variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "availability_zone" {
  type    = string
  default = "us-east-1b"
}

variable "availability_zone_b" {
  type    = string
  default = "us-east-1c"
}

variable "single_az_mode" {
  type    = bool
  default = false
}

variable "enable_nat_gateway" {
  type        = bool
  description = "Enable NAT Gateway to allow private ECS tasks outbound internet access (required for Stripe/Cognito hosted endpoints)."
  default     = true
}

variable "enable_vpc_endpoints" {
  type        = bool
  description = "Enable interface VPC endpoints. Keep false with NAT to reduce hourly PrivateLink costs."
  default     = false
}

variable "vpc_cidr" {
  type    = string
  default = "10.0.0.0/16"
}

variable "public_subnet_cidr" {
  type    = string
  default = "10.0.1.0/24"
}

variable "public_subnet_cidr_b" {
  type    = string
  default = "10.0.2.0/24"
}

variable "private_subnet_cidr" {
  type    = string
  default = "10.0.10.0/24"
}

variable "private_subnet_cidr_b" {
  type    = string
  default = "10.0.11.0/24"
}

variable "project_name" {
  type    = string
  default = "vizier-inference"
}

variable "github_repo" {
  type    = string
  default = "antonio-qsneto/vizier-inference-api"
}

variable "github_branch" {
  type    = string
  default = "main"
}

variable "environment" {
  type    = string
  default = "prod"
}

variable "frontend_upload_allowed_origins" {
  type = list(string)
  default = [
    "https://viziermed.com",
    "https://www.viziermed.com",
    "http://localhost:3000",
    "http://localhost:5173",
  ]
}

variable "django_allowed_hosts" {
  type    = string
  default = "*"
}

variable "alb_ingress_cidrs" {
  type = list(string)
  default = [
    "0.0.0.0/0",
  ]
}

variable "s3_artifacts_bucket_name" {
  type    = string
  default = null
}

variable "s3_kms_key_arn" {
  type    = string
  default = null
}

variable "jobs_queue_name" {
  type    = string
  default = "vizier-inference-jobs-prod"
}

variable "jobs_dlq_name" {
  type    = string
  default = "vizier-inference-jobs-prod-dlq"
}

variable "backend_ecr_repo_name" {
  type    = string
  default = "vizier-backend"
}

variable "biomedparse_ecr_repo_name" {
  type    = string
  default = "vizier-biomedparse"
}

variable "manage_backend_ecr_repository" {
  type    = bool
  default = false
}

variable "external_backend_ecr_repository_url" {
  type    = string
  default = ""
}

variable "manage_biomedparse_ecr_repository" {
  type    = bool
  default = false
}

variable "external_biomedparse_ecr_repository_url" {
  type    = string
  default = ""
}

variable "ecr_force_delete" {
  type    = bool
  default = false
}

variable "backend_image_tag" {
  type    = string
  default = "latest"
}

variable "biomedparse_image_tag" {
  type    = string
  default = "latest"
}

variable "biomedparse_image_override" {
  type    = string
  default = ""
}

variable "api_desired_count" {
  type    = number
  default = 2
}

variable "worker_desired_count" {
  type    = number
  default = 2
}

variable "api_cpu" {
  type    = number
  default = 1024
}

variable "api_memory" {
  type    = number
  default = 2048
}

variable "worker_cpu" {
  type    = number
  default = 1024
}

variable "worker_memory" {
  type    = number
  default = 2048
}

variable "rds_instance_identifier" {
  type    = string
  default = "vizier-postgres-prod"
}

variable "rds_db_name" {
  type    = string
  default = "vizier_med"
}

variable "rds_username" {
  type    = string
  default = "vizier_user"
}

variable "rds_password" {
  type      = string
  sensitive = true
}

variable "rds_instance_class" {
  type    = string
  default = "db.t4g.medium"
}

variable "rds_allocated_storage" {
  type    = number
  default = 100
}

variable "rds_backup_retention_days" {
  type    = number
  default = 7
}

variable "rds_skip_final_snapshot" {
  type    = bool
  default = false
}

variable "rds_final_snapshot_identifier" {
  type    = string
  default = ""
}

variable "rds_deletion_protection" {
  type    = bool
  default = true
}

variable "django_secret_key" {
  type      = string
  sensitive = true
}

variable "inference_api_bearer_token" {
  type      = string
  sensitive = true
  default   = ""
}

variable "enable_stripe_billing" {
  type        = bool
  description = "Enable Stripe billing endpoints in Django."
  default     = false
}

variable "stripe_secret_key" {
  type        = string
  description = "Stripe secret API key (sk_...)."
  sensitive   = true
  default     = ""
}

variable "stripe_webhook_secret" {
  type        = string
  description = "Stripe webhook endpoint signing secret (whsec_...)."
  sensitive   = true
  default     = ""
}

variable "stripe_product_id" {
  type        = string
  description = "Stripe product id used as fallback for price resolution."
  default     = ""
}

variable "stripe_price_id_individual_monthly" {
  type        = string
  description = "Stripe price id for individual monthly plan."
  default     = ""
}

variable "stripe_price_id_individual_annual" {
  type        = string
  description = "Stripe price id for individual annual plan."
  default     = ""
}

variable "stripe_price_lookup_key_individual_monthly" {
  type        = string
  description = "Stripe lookup key for individual monthly price."
  default     = ""
}

variable "stripe_price_lookup_key_individual_annual" {
  type        = string
  description = "Stripe lookup key for individual annual price."
  default     = ""
}

variable "stripe_allowed_redirect_origins" {
  type        = list(string)
  description = "Allowed frontend origins for Stripe checkout/portal redirect URLs."
  default     = []
}

variable "gpu_ami_id" {
  type    = string
  default = "ami-0b2483db0c00858b5"
}

variable "gpu_instance_type" {
  type    = string
  default = "g4dn.xlarge"
}

variable "gpu_asg_min" {
  type    = number
  default = 1
}

variable "gpu_asg_desired" {
  type    = number
  default = 1
}

variable "gpu_asg_max" {
  type    = number
  default = 1
}

variable "gpu_enable_business_hours_schedule" {
  type    = bool
  default = true
}

variable "gpu_business_hours_time_zone" {
  type    = string
  default = "America/Sao_Paulo"
}

variable "gpu_business_hours_scale_up_cron" {
  type    = string
  default = "0 7 * * *"
}

variable "gpu_business_hours_scale_down_cron" {
  type    = string
  default = "0 18 * * *"
}

variable "gpu_business_hours_min_size" {
  type    = number
  default = 1
}

variable "gpu_business_hours_desired_capacity" {
  type    = number
  default = 1
}

variable "bio_ecs_task_poll_seconds" {
  type    = number
  default = 15
}

variable "bio_ecs_task_timeout_seconds" {
  type    = number
  default = 3600
}

variable "cognito_callback_urls" {
  type = list(string)
  default = [
    "https://oauth.pstmn.io/v1/callback",
    "http://localhost:3000/auth/callback",
    "http://localhost:8000/auth/callback",
    "https://viziermed.com/auth/callback",
  ]
}

variable "cognito_logout_urls" {
  type = list(string)
  default = [
    "http://localhost:3000/login",
    "http://localhost:8000/",
    "https://viziermed.com/login",
  ]
}

variable "cognito_mfa_configuration" {
  type    = string
  default = "OFF"
}

variable "cognito_ses_source_arn" {
  type    = string
  default = null
}

variable "cluster_name" {
  type = string
}

variable "private_subnet_ids" {
  type = list(string)
}

variable "ecs_sg_id" {
  type = string
}

variable "instance_profile_name" {
  type = string
}

variable "gpu_ami_id" {
  type        = string
  description = "Optional custom AMI ID for GPU nodes. Leave empty/null to use AWS ECS GPU-optimized AMI from SSM."
  default     = null
}

variable "gpu_ami_ssm_parameter" {
  type        = string
  description = "SSM parameter that publishes the recommended AWS ECS GPU-optimized AMI."
  default     = "/aws/service/ecs/optimized-ami/amazon-linux-2/gpu/recommended/image_id"
}

variable "instance_type" {
  type    = string
  default = "g4dn.xlarge"
}

variable "root_volume_size_gb" {
  type    = number
  default = 200
}

variable "asg_min" {
  type    = number
  default = 1
}

variable "asg_desired" {
  type    = number
  default = 1
}

variable "asg_max" {
  type    = number
  default = 1
}

variable "enable_business_hours_schedule" {
  type    = bool
  default = true
}

variable "business_hours_time_zone" {
  type    = string
  default = "America/Sao_Paulo"
}

variable "business_hours_scale_up_cron" {
  type    = string
  default = "0 7 * * *"
}

variable "business_hours_scale_down_cron" {
  type    = string
  default = "0 18 * * *"
}

variable "business_hours_min_size" {
  type    = number
  default = 1
}

variable "business_hours_desired_capacity" {
  type    = number
  default = 1
}

variable "off_hours_min_size" {
  type    = number
  default = 0
}

variable "off_hours_desired_capacity" {
  type    = number
  default = 0
}

variable "off_hours_max_size" {
  type    = number
  default = 1
}

variable "biomedparse_image" {
  type = string
}

variable "biomedparse_container_name" {
  type    = string
  default = "biomedparse"
}

variable "biomedparse_gpu_count" {
  type    = number
  default = 1
}

variable "biomedparse_cpu" {
  type    = number
  default = 4096
}

variable "biomedparse_memory" {
  type    = number
  default = 14336
}

variable "biomedparse_log_group_name" {
  type    = string
  default = "/ecs/vizier-biomedparse"
}

variable "biomedparse_log_retention_days" {
  type    = number
  default = 30
}

variable "worker_task_execution_role_arn" {
  type = string
}

variable "worker_task_role_arn" {
  type = string
}

variable "aws_region" {
  type = string
}

variable "tags" {
  type    = map(string)
  default = {}
}

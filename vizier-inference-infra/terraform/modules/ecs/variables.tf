variable "cluster_name" { type = string }

variable "container_image" { type = string }

variable "vpc_id" { type = string }

variable "subnet_ids" { type = list(string) }

variable "security_group_id" { type = string }

variable "execution_role_arn" { type = string }

variable "task_role_arn" { type = string }

variable "efs_id" { type = string }

variable "efs_access_point_id" { type = string }

variable "sqs_queue_url" { type = string }

variable "aws_region" { type = string }

variable "cpu_capacity_provider_name" { type = string }

variable "service_discovery_namespace_name" {
  type    = string
  default = "internal"
}

# Optional: use an existing Cloud Map namespace instead of creating one.
variable "service_discovery_namespace_id" {
  type    = string
  default = ""
}

variable "service_discovery_service_name" {
  type    = string
  default = "api"
}

variable "tags" {
  type    = map(string)
  default = {}
}

variable "name" {
  type = string
}

variable "cluster_name" {
  type = string
}

variable "execution_role_arn" {
  type = string
}

variable "task_role_arn" {
  type = string
}

variable "container_image" {
  type = string
}

variable "container_port" {
  type    = number
  default = 0
}

variable "command" {
  type    = list(string)
  default = []
}

variable "cpu" {
  type    = number
  default = 1024
}

variable "memory" {
  type    = number
  default = 2048
}

variable "desired_count" {
  type    = number
  default = 1
}

variable "subnet_ids" {
  type = list(string)
}

variable "security_group_ids" {
  type = list(string)
}

variable "assign_public_ip" {
  type    = bool
  default = false
}

variable "target_group_arn" {
  type    = string
  default = ""
}

variable "health_check_grace_period_seconds" {
  type    = number
  default = 0
}

variable "aws_region" {
  type = string
}

variable "log_group_name" {
  type    = string
  default = ""
}

variable "environment" {
  type    = map(string)
  default = {}
}

variable "secrets" {
  type = list(object({
    name      = string
    valueFrom = string
  }))
  default = []
}

variable "tags" {
  type    = map(string)
  default = {}
}

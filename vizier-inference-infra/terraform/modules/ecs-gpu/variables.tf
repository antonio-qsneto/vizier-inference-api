variable "cluster_name" {
  type = string
}

variable "vpc_id" {
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
  description = "Baked ECS GPU AMI ID used by g4dn worker nodes"
}

variable "instance_type" {
  type = string
  # default = "inf2.xlarge"
  default = "g4dn.xlarge"
}

variable "cpu_instance_type" {
  type    = string
  default = "t3.medium"
}

variable "asg_min" {
  type    = number
  default = 0
}

variable "asg_desired" {
  type    = number
  default = 0
}

variable "asg_max" {
  type    = number
  default = 2
}

variable "cpu_asg_min" {
  type    = number
  default = 1
}

variable "cpu_asg_desired" {
  type    = number
  default = 1
}

variable "cpu_asg_max" {
  type    = number
  default = 2
}

variable "tags" {
  type    = map(string)
  default = {}
}

variable "worker_image" {
  type = string
}

variable "biomedparse_image" {
  type = string
}

variable "worker_task_execution_role_arn" {
  type = string
}

variable "worker_task_role_arn" {
  type = string
}

variable "sqs_queue_url" {
  type = string
}

variable "jobs_table_name" {
  type = string
}

variable "artifacts_bucket" {
  type = string
}

variable "aws_region" {
  type = string
}

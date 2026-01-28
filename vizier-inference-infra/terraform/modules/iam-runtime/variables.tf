variable "sqs_queue_arn" { type = string }

variable "efs_id" {
  type        = string
  description = "EFS filesystem ID for task IAM access"
}

variable "tags" {
  type    = map(string)
  default = {}
}

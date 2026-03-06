variable "table_name" {
  type        = string
  description = "DynamoDB table name for inference jobs"
}

variable "enable_point_in_time_recovery" {
  type        = bool
  description = "Enable point-in-time recovery for the table"
  default     = true
}

variable "kms_key_arn" {
  type        = string
  description = "Optional KMS key ARN for DynamoDB encryption"
  default     = null
}

variable "tags" {
  type    = map(string)
  default = {}
}

variable "name" {
  type        = string
  description = "Name of the SQS queue"
}

variable "visibility_timeout_seconds" {
  type        = number
  default     = 900
  description = "Max processing time for a job (BiomedParse inference)"
}

variable "message_retention_seconds" {
  type        = number
  default     = 86400
  description = "How long messages stay in queue (24h)"
}

variable "receive_wait_time_seconds" {
  type        = number
  default     = 10
  description = "Long polling duration"
}

variable "create_dlq" {
  type        = bool
  description = "Create and attach a dead-letter queue"
  default     = true
}

variable "dlq_name" {
  type        = string
  description = "Optional DLQ name. Defaults to <name>-dlq"
  default     = null
}

variable "dlq_message_retention_seconds" {
  type        = number
  description = "Retention period for DLQ messages"
  default     = 1209600
}

variable "max_receive_count" {
  type        = number
  description = "How many receives before moving to DLQ"
  default     = 5
}

variable "tags" {
  type    = map(string)
  default = {}
}

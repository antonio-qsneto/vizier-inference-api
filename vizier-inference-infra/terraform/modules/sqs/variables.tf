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

variable "tags" {
  type        = map(string)
  default     = {}
}

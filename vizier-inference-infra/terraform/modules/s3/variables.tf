variable "bucket_name" {
  type        = string
  description = "Name of the artifacts bucket"
}

variable "force_destroy" {
  type        = bool
  description = "Allow bucket destruction even when objects exist"
  default     = false
}

variable "enable_versioning" {
  type        = bool
  description = "Enable bucket versioning"
  default     = true
}

variable "kms_key_arn" {
  type        = string
  description = "Optional KMS key ARN for bucket encryption"
  default     = null
}

variable "tags" {
  type    = map(string)
  default = {}
}

variable "cors_allowed_origins" {
  type        = list(string)
  description = "Allowed origins for browser uploads/downloads"
  default     = []
}

variable "lifecycle_noncurrent_days" {
  type        = number
  description = "Days to keep noncurrent object versions"
  default     = 30
}

variable "lifecycle_expiration_days" {
  type        = number
  description = "Days to expire audit/temporary prefixes"
  default     = 365
}

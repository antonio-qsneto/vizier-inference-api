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

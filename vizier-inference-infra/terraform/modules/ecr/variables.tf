variable "name" {
  type = string
}

variable "force_delete" {
  type    = bool
  default = false
}

variable "image_tag_mutability" {
  type    = string
  default = "MUTABLE"
}

variable "lifecycle_max_image_count" {
  type    = number
  default = 30
}

variable "kms_key_arn" {
  type    = string
  default = null
}

variable "tags" {
  type    = map(string)
  default = {}
}

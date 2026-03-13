variable "name" {
  type = string
}

variable "description" {
  type    = string
  default = ""
}

variable "secret_string" {
  type      = string
  sensitive = true
}

variable "kms_key_id" {
  type    = string
  default = null
}

variable "tags" {
  type    = map(string)
  default = {}
}

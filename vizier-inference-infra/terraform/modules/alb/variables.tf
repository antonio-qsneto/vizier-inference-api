variable "name" {
  type = string
}

variable "vpc_id" {
  type = string
}

variable "public_subnet_ids" {
  type = list(string)
}

variable "ingress_cidrs" {
  type    = list(string)
  default = ["0.0.0.0/0"]
}

variable "listener_port" {
  type    = number
  default = 80
}

variable "target_port" {
  type    = number
  default = 8000
}

variable "health_check_path" {
  type    = string
  default = "/api/health/"
}

variable "tags" {
  type    = map(string)
  default = {}
}

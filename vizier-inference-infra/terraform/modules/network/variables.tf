variable "vpc_cidr" {
  description = "CIDR block for the VPC"
  type        = string
}

variable "public_subnet_cidr" {
  type    = string
  default = "10.0.1.0/24"
}

variable "public_subnet_cidr_b" {
  type    = string
  default = "10.0.2.0/24"
}

variable "private_subnet_cidr" {
  type    = string
  default = "10.0.10.0/24"
}

variable "private_subnet_cidr_b" {
  type    = string
  default = "10.0.11.0/24"
}

variable "availability_zone" {
  type    = string
  default = "us-east-1a"
}

variable "availability_zone_b" {
  type    = string
  default = "us-east-1b"
}

variable "enable_nat_gateway" {
  description = "Enable NAT Gateway for private subnet internet access"
  type        = bool
  default     = true
}

variable "enable_vpc_endpoints" {
  description = "Enable VPC endpoints (recommended when NAT is disabled)"
  type        = bool
  default     = true
}

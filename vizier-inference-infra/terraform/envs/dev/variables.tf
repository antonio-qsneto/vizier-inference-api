variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "availability_zone" {
  type    = string
  default = "us-east-1a"
}

variable "vpc_cidr" {
  type    = string
  default = "10.0.0.0/16"
}

variable "api_image" {
  type        = string
  description = "ECR image URI for the FastAPI container"
}

variable "worker_image" {
  type        = string
  description = "ECR image URI for the GPU worker container"
}

variable "biomedparse_image" {
  type        = string
  description = "ECR image URI for the BiomedParse model container"
}

variable "sqs_queue_arn" {
  type = string
}

variable "artifacts_bucket_arn" {
  type = string
}

variable "app_secret_arns" {
  type    = list(string)
  default = []
}

variable "name_prefix" {
  type    = string
  default = "vizier"
}

variable "biomedparse_cluster_arn" {
  type    = string
  default = ""
}

variable "biomedparse_task_definition_arn" {
  type    = string
  default = ""
}

variable "tags" {
  type    = map(string)
  default = {}
}

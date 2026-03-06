variable "sqs_queue_arn" { type = string }

variable "jobs_table_arn" {
  type        = string
  description = "DynamoDB jobs table ARN"
}

variable "artifacts_bucket_arn" {
  type        = string
  description = "S3 artifacts bucket ARN"
}

variable "job_artifacts_prefix" {
  type        = string
  description = "Artifacts prefix within the bucket"
}

variable "tags" {
  type    = map(string)
  default = {}
}

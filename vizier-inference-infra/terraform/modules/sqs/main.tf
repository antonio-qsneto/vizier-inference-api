resource "aws_sqs_queue" "this" {
  name = var.name

  visibility_timeout_seconds = var.visibility_timeout_seconds
  message_retention_seconds  = var.message_retention_seconds
  receive_wait_time_seconds  = var.receive_wait_time_seconds

  # IMPORTANT: medical workloads benefit from this
  sqs_managed_sse_enabled = true

  tags = var.tags
}

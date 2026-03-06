resource "aws_sqs_queue" "dlq" {
  count = var.create_dlq ? 1 : 0

  name = coalesce(var.dlq_name, "${var.name}-dlq")

  message_retention_seconds = var.dlq_message_retention_seconds
  sqs_managed_sse_enabled   = true
  tags                      = var.tags
}

resource "aws_sqs_queue" "this" {
  name = var.name

  visibility_timeout_seconds = var.visibility_timeout_seconds
  message_retention_seconds  = var.message_retention_seconds
  receive_wait_time_seconds  = var.receive_wait_time_seconds

  redrive_policy = var.create_dlq ? jsonencode({
    deadLetterTargetArn = aws_sqs_queue.dlq[0].arn
    maxReceiveCount     = var.max_receive_count
  }) : null

  # IMPORTANT: medical workloads benefit from this
  sqs_managed_sse_enabled = true

  tags = var.tags
}

resource "aws_sqs_queue_redrive_allow_policy" "dlq" {
  count = var.create_dlq ? 1 : 0

  queue_url = aws_sqs_queue.dlq[0].id
  redrive_allow_policy = jsonencode({
    redrivePermission = "byQueue"
    sourceQueueArns   = [aws_sqs_queue.this.arn]
  })
}

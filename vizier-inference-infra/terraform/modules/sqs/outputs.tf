output "queue_url" {
  value = aws_sqs_queue.this.url
}

output "queue_arn" {
  value = aws_sqs_queue.this.arn
}

output "queue_name" {
  value = aws_sqs_queue.this.name
}

output "dlq_url" {
  value = var.create_dlq ? aws_sqs_queue.dlq[0].url : null
}

output "dlq_arn" {
  value = var.create_dlq ? aws_sqs_queue.dlq[0].arn : null
}

output "dlq_name" {
  value = var.create_dlq ? aws_sqs_queue.dlq[0].name : null
}

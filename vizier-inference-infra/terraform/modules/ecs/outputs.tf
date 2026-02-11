output "task_definition_arn" {
  value = aws_ecs_task_definition.api.arn
}

output "service_discovery_namespace_id" {
  value = local.service_discovery_namespace_id
}

output "service_discovery_service_name" {
  value = aws_service_discovery_service.api.name
}

output "service_discovery_dns_name" {
  value = "${aws_service_discovery_service.api.name}.${var.service_discovery_namespace_name}"
}

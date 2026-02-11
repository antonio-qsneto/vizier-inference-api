output "region" {
  value = var.aws_region
}

output "jobs_queue_url" { value = module.sqs.queue_url }
output "jobs_queue_arn" { value = module.sqs.queue_arn }

output "ecs_cluster_name" { value = module.ecs_gpu.cluster_name }
output "ecs_capacity_provider" { value = module.ecs_gpu.capacity_provider_name }
output "gpu_asg_name" { value = module.ecs_gpu.asg_name }

output "api_task_role_arn" { value = module.iam_runtime.api_task_role_arn }
output "worker_task_role_arn" { value = module.iam_runtime.worker_task_role_arn }
output "ecs_task_execution_role_arn" { value = module.iam_runtime.ecs_task_execution_role_arn }

output "api_service_discovery_dns" {
  value = module.ecs.service_discovery_dns_name
}

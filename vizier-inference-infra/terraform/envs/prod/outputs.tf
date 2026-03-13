output "region" {
  value = var.aws_region
}

output "alb_dns_name" {
  value = module.alb.alb_dns_name
}

output "alb_arn" {
  value = module.alb.alb_arn
}

output "jobs_queue_url" {
  value = module.sqs.queue_url
}

output "jobs_queue_arn" {
  value = module.sqs.queue_arn
}

output "jobs_dlq_url" {
  value = module.sqs.dlq_url
}

output "jobs_dlq_arn" {
  value = module.sqs.dlq_arn
}

output "artifacts_bucket_name" {
  value = module.s3.bucket_name
}

output "artifacts_bucket_arn" {
  value = module.s3.bucket_arn
}

output "backend_ecr_repository_url" {
  value = local.backend_ecr_repository_url
}

output "biomedparse_ecr_repository_url" {
  value = local.biomedparse_ecr_repository_url
}

output "ecs_gpu_cluster_name" {
  value = module.ecs_gpu.cluster_name
}

output "ecs_gpu_capacity_provider" {
  value = module.ecs_gpu.capacity_provider_name
}

output "ecs_gpu_biomedparse_task_definition_arn" {
  value = module.ecs_gpu.biomedparse_task_def_arn
}

output "ecs_gpu_asg_name" {
  value = module.ecs_gpu.asg_name
}

output "ecs_fargate_django_service_name" {
  value = module.ecs_fargate_django.service_name
}

output "ecs_fargate_django_task_definition_arn" {
  value = module.ecs_fargate_django.task_definition_arn
}

output "ecs_fargate_worker_service_name" {
  value = module.ecs_fargate_worker.service_name
}

output "rds_endpoint" {
  value = module.rds_postgres.endpoint
}

output "rds_port" {
  value = module.rds_postgres.port
}

output "rds_instance_id" {
  value = module.rds_postgres.instance_id
}

output "rds_security_group_id" {
  value = module.rds_postgres.security_group_id
}

output "django_app_secret_arn" {
  value = module.app_secrets.secret_arn
}

output "private_subnet_ids" {
  value = module.network.private_subnet_ids
}

output "fargate_app_security_group_id" {
  value = aws_security_group.fargate_app.id
}

output "cognito_user_pool_id" {
  value = module.cognito.user_pool_id
}

output "cognito_user_pool_client_id" {
  value = module.cognito.user_pool_client_id
}

output "cognito_user_pool_domain" {
  value = module.cognito.user_pool_domain
}

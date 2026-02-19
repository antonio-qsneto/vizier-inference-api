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

output "cognito_user_pool_id" {
  value = module.cognito.user_pool_id
}

output "cognito_user_pool_arn" {
  value = module.cognito.user_pool_arn
}

output "cognito_user_pool_client_id" {
  value = module.cognito.user_pool_client_id
}

output "cognito_user_pool_domain" {
  value = module.cognito.user_pool_domain
}

output "cognito_hosted_ui_base_url" {
  value = "https://${module.cognito.user_pool_domain}.auth.${var.aws_region}.amazoncognito.com"
}

output "cognito_oauth_authorize_url_example" {
  value = "https://${module.cognito.user_pool_domain}.auth.${var.aws_region}.amazoncognito.com/oauth2/authorize?client_id=${module.cognito.user_pool_client_id}&response_type=code&scope=${urlencode("openid email profile")}&redirect_uri=${urlencode(var.cognito_callback_urls[0])}"
}

output "cognito_oauth_token_url" {
  value = "https://${module.cognito.user_pool_domain}.auth.${var.aws_region}.amazoncognito.com/oauth2/token"
}

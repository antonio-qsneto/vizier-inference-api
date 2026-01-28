output "ecs_instance_profile_name" {
  value = aws_iam_instance_profile.ecs.name
}

output "ecs_task_execution_role_arn" {
  value = aws_iam_role.ecs_task_execution_role.arn
}

output "api_task_role_arn" {
  value = aws_iam_role.api_task_role.arn
}

output "worker_task_role_arn" {
  value = aws_iam_role.worker_task_role.arn
}

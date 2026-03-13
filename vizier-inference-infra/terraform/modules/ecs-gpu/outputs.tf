output "cluster_name" {
  value = aws_ecs_cluster.this.name
}

output "ecs_cluster_name" {
  value = aws_ecs_cluster.this.name
}

output "cluster_arn" {
  value = aws_ecs_cluster.this.arn
}

output "capacity_provider_name" {
  value = aws_ecs_capacity_provider.gpu.name
}

output "gpu_capacity_provider_name" {
  value = aws_ecs_capacity_provider.gpu.name
}

output "asg_name" {
  value = aws_autoscaling_group.gpu.name
}

output "gpu_asg_name" {
  value = aws_autoscaling_group.gpu.name
}

output "biomedparse_task_def_arn" {
  value = aws_ecs_task_definition.biomedparse.arn
}

output "biomedparse_task_definition_arn" {
  value = aws_ecs_task_definition.biomedparse.arn
}

output "biomedparse_log_group_name" {
  value = aws_cloudwatch_log_group.biomedparse.name
}

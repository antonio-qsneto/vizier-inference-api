output "cluster_name" {
  value = aws_ecs_cluster.this.name
}

output "capacity_provider_name" {
  value = aws_ecs_capacity_provider.gpu.name
}

output "asg_name" {
  value = aws_autoscaling_group.gpu.name
}

output "cpu_capacity_provider_name" {
  value = aws_ecs_capacity_provider.cpu.name
}

output "biomedparse_task_def_arn" {
  value = aws_ecs_task_definition.biomedparse.arn
}

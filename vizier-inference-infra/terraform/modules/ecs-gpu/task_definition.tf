resource "aws_cloudwatch_log_group" "biomedparse" {
  name              = var.biomedparse_log_group_name
  retention_in_days = var.biomedparse_log_retention_days

  tags = var.tags
}

resource "aws_ecs_task_definition" "biomedparse" {
  family                   = "vizier-biomedparse"
  network_mode             = "awsvpc"
  requires_compatibilities = ["EC2"]
  cpu                      = tostring(var.biomedparse_cpu)
  memory                   = tostring(var.biomedparse_memory)

  execution_role_arn = var.worker_task_execution_role_arn
  task_role_arn      = var.worker_task_role_arn

  container_definitions = jsonencode([
    {
      name      = var.biomedparse_container_name
      image     = var.biomedparse_image
      essential = true

      entryPoint = [
        "/bin/sh",
        "-lc"
      ]

      command = [
        "echo '{\"event\":\"missing_command_override\"}' >&2; exit 2"
      ]

      resourceRequirements = [
        {
          type  = "GPU"
          value = tostring(var.biomedparse_gpu_count)
        }
      ]

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          awslogs-group         = aws_cloudwatch_log_group.biomedparse.name
          awslogs-region        = var.aws_region
          awslogs-stream-prefix = "biomedparse"
        }
      }
    }
  ])
}

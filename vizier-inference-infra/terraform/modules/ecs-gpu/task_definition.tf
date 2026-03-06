resource "aws_ecs_task_definition" "worker" {
  family                   = "vizier-worker"
  network_mode             = "awsvpc"
  requires_compatibilities = ["EC2"]
  cpu                      = "1024"
  memory                   = "2048"

  execution_role_arn = var.worker_task_execution_role_arn
  task_role_arn      = var.worker_task_role_arn

  container_definitions = jsonencode([
    {
      name      = "worker"
      image     = var.worker_image
      essential = true

      environment = [
        { name = "SQS_QUEUE_URL", value = var.sqs_queue_url },
        { name = "JOBS_TABLE_NAME", value = var.jobs_table_name },
        { name = "ARTIFACTS_BUCKET", value = var.artifacts_bucket },
        { name = "AWS_REGION", value = var.aws_region },
        { name = "ECS_CLUSTER", value = var.cluster_name },
        { name = "BIO_TASK_DEF", value = aws_ecs_task_definition.biomedparse.arn },
        { name = "TASK_SUBNETS", value = join(",", var.private_subnet_ids) },
        { name = "TASK_SECURITY_GROUPS", value = var.ecs_sg_id },
        { name = "CAPACITY_PROVIDER", value = aws_ecs_capacity_provider.gpu.name }
      ]

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          awslogs-group         = "/ecs/vizier-worker"
          awslogs-region        = var.aws_region
          awslogs-stream-prefix = "worker"
        }
      }
    }
  ])
}

# BiomedParse GPU task definition (ephemeral per job)
resource "aws_ecs_task_definition" "biomedparse" {
  family                   = "vizier-biomedparse"
  network_mode             = "awsvpc"
  requires_compatibilities = ["EC2"]
  cpu                      = "4096"
  memory                   = "14336"

  execution_role_arn = var.worker_task_execution_role_arn
  task_role_arn      = var.worker_task_role_arn

  container_definitions = jsonencode([
    {
      name      = "biomedparse"
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
          value = "1"
        }
      ]

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          awslogs-group         = "/ecs/vizier-biomedparse"
          awslogs-region        = var.aws_region
          awslogs-stream-prefix = "biomedparse"
        }
      }
    }
  ])
}

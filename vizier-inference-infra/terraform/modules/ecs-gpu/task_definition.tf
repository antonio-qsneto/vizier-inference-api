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
        { name = "JOB_BASE_DIR", value = "/mnt/efs/jobs" },
        { name = "SQS_QUEUE_URL", value = var.sqs_queue_url },
        { name = "AWS_REGION", value = var.aws_region },
        { name = "ECS_CLUSTER", value = var.cluster_name },
        { name = "BIO_TASK_DEF", value = aws_ecs_task_definition.biomedparse.arn },
        { name = "TASK_SUBNETS", value = join(",", var.private_subnet_ids) },
        { name = "TASK_SECURITY_GROUPS", value = var.ecs_sg_id },
        { name = "CAPACITY_PROVIDER", value = aws_ecs_capacity_provider.gpu.name }
      ]

      mountPoints = [
        {
          sourceVolume  = "efs-jobs"
          containerPath = "/mnt/efs"
          readOnly      = false
        }
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

  volume {
    name = "efs-jobs"

    efs_volume_configuration {
      file_system_id     = var.efs_id
      transit_encryption = "ENABLED"

      authorization_config {
        access_point_id = var.efs_access_point_id
        iam             = "ENABLED"
      }
    }
  }
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

      resourceRequirements = [
        {
          type  = "GPU"
          value = "1"
        }
      ]

      mountPoints = [
        {
          sourceVolume  = "efs-jobs"
          containerPath = "/mnt/efs"
          readOnly      = false
        }
      ]

      environment = [
        { name = "JOB_BASE_DIR", value = "/mnt/efs/jobs" }
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

  volume {
    name = "efs-jobs"

    efs_volume_configuration {
      file_system_id     = var.efs_id
      transit_encryption = "ENABLED"

      authorization_config {
        access_point_id = var.efs_access_point_id
        iam             = "ENABLED"
      }
    }
  }
}

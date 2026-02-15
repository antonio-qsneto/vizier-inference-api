resource "aws_ecs_task_definition" "api" {
  family                   = "vizier-api"
  network_mode             = "awsvpc"
  requires_compatibilities = ["EC2"]
  cpu                      = "1024"
  memory                   = "2048"

  execution_role_arn = var.execution_role_arn
  task_role_arn      = var.task_role_arn

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

  container_definitions = jsonencode([
    {
      name      = "api"
      image     = var.container_image
      essential = true

      mountPoints = [
        {
          sourceVolume  = "efs-jobs"
          containerPath = "/mnt/efs"
          readOnly      = false
        }
      ]

      portMappings = [
        { containerPort = 8000, protocol = "tcp" }
      ]

      environment = [
        { name = "JOB_BASE_DIR", value = "/mnt/efs/jobs" },
        { name = "SQS_QUEUE_URL", value = var.sqs_queue_url },
        { name = "AWS_REGION", value = var.aws_region }
      ]

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          awslogs-region        = "us-east-1"
          awslogs-group         = "/ecs/vizier-api"
          awslogs-stream-prefix = "api"
        }
      }
    }
  ])

  tags = var.tags
}

resource "aws_service_discovery_private_dns_namespace" "this" {
  count = var.service_discovery_namespace_id == "" ? 1 : 0

  name = var.service_discovery_namespace_name
  vpc  = var.vpc_id
  tags = var.tags
}

locals {
  service_discovery_namespace_id = var.service_discovery_namespace_id != "" ? var.service_discovery_namespace_id : aws_service_discovery_private_dns_namespace.this[0].id
}

resource "aws_service_discovery_service" "api" {
  name = var.service_discovery_service_name

  dns_config {
    namespace_id   = local.service_discovery_namespace_id
    routing_policy = "MULTIVALUE"

    dns_records {
      ttl  = 10
      type = "A"
    }
  }

  health_check_custom_config {
  }

  tags = var.tags
}

resource "aws_ecs_service" "api" {
  name            = "vizier-api"
  cluster         = var.cluster_name
  task_definition = aws_ecs_task_definition.api.arn
  desired_count   = 1

  network_configuration {
    subnets          = var.subnet_ids
    security_groups  = [var.security_group_id]
    assign_public_ip = false
  }

  service_registries {
    registry_arn   = aws_service_discovery_service.api.arn
    container_name = "api"
  }

  capacity_provider_strategy {
    capacity_provider = var.cpu_capacity_provider_name
    weight            = 1
    base              = 0
  }

  propagate_tags         = "TASK_DEFINITION"
  enable_execute_command = true
}

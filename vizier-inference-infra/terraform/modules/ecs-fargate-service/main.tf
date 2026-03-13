locals {
  resolved_log_group_name = var.log_group_name != "" ? var.log_group_name : "/ecs/${var.name}"
  port_mappings = var.container_port > 0 ? [
    {
      containerPort = var.container_port
      protocol      = "tcp"
    }
  ] : []
  environment_list = [
    for key, value in var.environment : {
      name  = key
      value = value
    }
  ]
}

resource "aws_cloudwatch_log_group" "this" {
  name              = local.resolved_log_group_name
  retention_in_days = 30

  tags = var.tags
}

resource "aws_ecs_task_definition" "this" {
  family                   = var.name
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = tostring(var.cpu)
  memory                   = tostring(var.memory)

  execution_role_arn = var.execution_role_arn
  task_role_arn      = var.task_role_arn

  container_definitions = jsonencode([
    {
      name         = var.name
      image        = var.container_image
      essential    = true
      command      = var.command
      environment  = local.environment_list
      secrets      = var.secrets
      portMappings = local.port_mappings
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          awslogs-group         = aws_cloudwatch_log_group.this.name
          awslogs-region        = var.aws_region
          awslogs-stream-prefix = var.name
        }
      }
    }
  ])

  tags = var.tags
}

resource "aws_ecs_service" "this" {
  name            = var.name
  cluster         = var.cluster_name
  task_definition = aws_ecs_task_definition.this.arn
  desired_count   = var.desired_count
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = var.subnet_ids
    security_groups  = var.security_group_ids
    assign_public_ip = var.assign_public_ip
  }

  enable_execute_command            = true
  propagate_tags                    = "TASK_DEFINITION"
  health_check_grace_period_seconds = var.health_check_grace_period_seconds

  dynamic "load_balancer" {
    for_each = var.target_group_arn != "" && var.container_port > 0 ? [1] : []
    content {
      target_group_arn = var.target_group_arn
      container_name   = var.name
      container_port   = var.container_port
    }
  }

  tags = var.tags
}

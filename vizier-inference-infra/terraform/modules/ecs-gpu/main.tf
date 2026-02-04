data "aws_region" "current" {}

data "aws_ami" "ecs_gpu" {
  most_recent = true
  owners      = ["amazon"]

  filter {
    name   = "name"
    values = ["amzn2-ami-ecs-gpu-hvm-*-x86_64-ebs"]
  }
}

resource "aws_ecs_cluster" "this" {
  name = var.cluster_name
  tags = var.tags
}

locals {
  user_data = <<-EOF
              #!/bin/bash
              echo "ECS_CLUSTER=${var.cluster_name}" >> /etc/ecs/ecs.config
              EOF
}

resource "aws_launch_template" "gpu" {
  name_prefix   = "${var.cluster_name}-gpu-"
  image_id      = data.aws_ami.ecs_gpu.id
  instance_type = var.instance_type

  iam_instance_profile {
    name = var.instance_profile_name
  }

  vpc_security_group_ids = [var.ecs_sg_id]
  user_data              = base64encode(local.user_data)

  block_device_mappings {
    device_name = "/dev/xvda"
    ebs {
      volume_size           = 200
      volume_type           = "gp3"
      delete_on_termination = true
    }
  }

  tag_specifications {
    resource_type = "instance"
    tags = merge(var.tags, {
      Name = "${var.cluster_name}-gpu"
    })
  }
}

resource "aws_autoscaling_group" "gpu" {
  name                = "${var.cluster_name}-gpu-asg"
  min_size            = var.asg_min
  desired_capacity    = var.asg_desired
  max_size            = var.asg_max
  vpc_zone_identifier = var.private_subnet_ids
  default_cooldown    = 60
  health_check_grace_period = 60

  launch_template {
    id      = aws_launch_template.gpu.id
    version = "$Latest"
  }

  tag {
    key                 = "AmazonECSManaged"
    value               = "true"
    propagate_at_launch = true
  }

  warm_pool {
    pool_state        = "Stopped"
    min_size          = var.warm_pool_min_size
    instance_reuse_policy {
      reuse_on_scale_in = true
    }
  }
}

resource "aws_launch_template" "cpu" {
  name_prefix   = "${var.cluster_name}-cpu-"
  image_id      = data.aws_ami.ecs_gpu.id
  instance_type = var.cpu_instance_type

  iam_instance_profile {
    name = var.instance_profile_name
  }

  vpc_security_group_ids = [var.ecs_sg_id]
  user_data              = base64encode(local.user_data)

  tag_specifications {
    resource_type = "instance"
    tags = merge(var.tags, {
      Name = "${var.cluster_name}-cpu"
    })
  }
}

resource "aws_autoscaling_group" "cpu" {
  name                = "${var.cluster_name}-cpu-asg"
  min_size            = var.cpu_asg_min
  desired_capacity    = var.cpu_asg_desired
  max_size            = var.cpu_asg_max
  vpc_zone_identifier = var.private_subnet_ids

  launch_template {
    id      = aws_launch_template.cpu.id
    version = "$Latest"
  }

  tag {
    key                 = "AmazonECSManaged"
    value               = "true"
    propagate_at_launch = true
  }
}

resource "aws_ecs_capacity_provider" "cpu" {
  name = "${var.cluster_name}-cpu-cp"

  auto_scaling_group_provider {
    auto_scaling_group_arn = aws_autoscaling_group.cpu.arn

    managed_scaling {
      status                    = "ENABLED"
      target_capacity           = 100
      minimum_scaling_step_size = 1
      maximum_scaling_step_size = 1
      instance_warmup_period    = 60
    }

    managed_termination_protection = "DISABLED"
  }
}

resource "aws_ecs_capacity_provider" "gpu" {
  name = "${var.cluster_name}-gpu-cp"

  auto_scaling_group_provider {
    auto_scaling_group_arn = aws_autoscaling_group.gpu.arn

    managed_scaling {
      status                    = "ENABLED"
      target_capacity           = 100
      minimum_scaling_step_size = 1
      maximum_scaling_step_size = 1
    }

    managed_termination_protection = "DISABLED"
  }
}

resource "aws_ecs_cluster_capacity_providers" "this" {
  cluster_name       = aws_ecs_cluster.this.name
  capacity_providers = [
    aws_ecs_capacity_provider.gpu.name,
    aws_ecs_capacity_provider.cpu.name
  ]

  default_capacity_provider_strategy {
    capacity_provider = aws_ecs_capacity_provider.cpu.name
    weight            = 1
    base              = 0
  }
}

resource "aws_ecs_service" "worker" {
  name            = "vizier-worker"
  cluster         = aws_ecs_cluster.this.id
  task_definition = aws_ecs_task_definition.worker.arn
  desired_count   = 1

  capacity_provider_strategy {
    capacity_provider = aws_ecs_capacity_provider.cpu.name
    weight            = 1
  }

  network_configuration {
    subnets          = var.private_subnet_ids
    security_groups  = [var.ecs_sg_id]
    assign_public_ip = false
  }

  propagate_tags         = "TASK_DEFINITION"
  enable_execute_command = true
}

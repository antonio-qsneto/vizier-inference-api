resource "aws_ecs_cluster" "this" {
  name = var.cluster_name
  tags = var.tags
}

locals {
  gpu_user_data = <<-EOF
              #!/bin/bash
              echo "ECS_CLUSTER=${var.cluster_name}" >> /etc/ecs/ecs.config
              echo "ECS_IMAGE_PULL_BEHAVIOR=prefer-cached" >> /etc/ecs/ecs.config
              echo "ECS_DISABLE_IMAGE_CLEANUP=true" >> /etc/ecs/ecs.config
              EOF
}

resource "aws_launch_template" "gpu" {
  name_prefix   = "${var.cluster_name}-gpu-"
  image_id      = var.gpu_ami_id
  instance_type = var.instance_type

  iam_instance_profile {
    name = var.instance_profile_name
  }

  vpc_security_group_ids = [var.ecs_sg_id]
  user_data              = base64encode(local.gpu_user_data)

  block_device_mappings {
    device_name = "/dev/xvda"
    ebs {
      volume_size           = var.root_volume_size_gb
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
  name                      = "${var.cluster_name}-gpu-asg"
  min_size                  = var.asg_min
  desired_capacity          = var.asg_desired
  max_size                  = var.asg_max
  vpc_zone_identifier       = var.private_subnet_ids
  default_cooldown          = 60
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
}

resource "aws_ecs_capacity_provider" "gpu" {
  name = "${var.cluster_name}-gpu-cp"

  auto_scaling_group_provider {
    auto_scaling_group_arn = aws_autoscaling_group.gpu.arn

    managed_scaling {
      status                    = "ENABLED"
      target_capacity           = 100
      minimum_scaling_step_size = 1
      maximum_scaling_step_size = 2
      instance_warmup_period    = 120
    }

    managed_termination_protection = "DISABLED"
  }
}

resource "aws_ecs_cluster_capacity_providers" "this" {
  cluster_name = aws_ecs_cluster.this.name
  capacity_providers = [
    aws_ecs_capacity_provider.gpu.name
  ]

  default_capacity_provider_strategy {
    capacity_provider = aws_ecs_capacity_provider.gpu.name
    weight            = 1
    base              = 0
  }
}

resource "aws_autoscaling_schedule" "business_hours_scale_up" {
  count = var.enable_business_hours_schedule ? 1 : 0

  scheduled_action_name  = "${var.cluster_name}-gpu-business-hours-up"
  autoscaling_group_name = aws_autoscaling_group.gpu.name
  min_size               = var.business_hours_min_size
  desired_capacity       = var.business_hours_desired_capacity
  max_size               = var.asg_max
  recurrence             = var.business_hours_scale_up_cron
  time_zone              = var.business_hours_time_zone
}

resource "aws_autoscaling_schedule" "business_hours_scale_down" {
  count = var.enable_business_hours_schedule ? 1 : 0

  scheduled_action_name  = "${var.cluster_name}-gpu-business-hours-down"
  autoscaling_group_name = aws_autoscaling_group.gpu.name
  min_size               = var.asg_min
  desired_capacity       = var.asg_desired
  max_size               = var.asg_max
  recurrence             = var.business_hours_scale_down_cron
  time_zone              = var.business_hours_time_zone
}

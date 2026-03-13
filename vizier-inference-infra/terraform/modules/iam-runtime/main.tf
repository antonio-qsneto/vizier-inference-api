# -----------------------------
# Shared assume-role policy for ECS tasks
# -----------------------------
data "aws_iam_policy_document" "ecs_task_assume" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

# -----------------------------
# ECS EC2 instance role (for GPU cluster)
# -----------------------------
data "aws_iam_policy_document" "ecs_instance_assume" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "ecs_instance_role" {
  name               = "${var.name_prefix}-ecs-instance-role"
  assume_role_policy = data.aws_iam_policy_document.ecs_instance_assume.json
  tags               = var.tags
}

resource "aws_iam_role_policy_attachment" "ecs_instance" {
  role       = aws_iam_role.ecs_instance_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonEC2ContainerServiceforEC2Role"
}

resource "aws_iam_role_policy_attachment" "ecs_instance_ecr_read" {
  role       = aws_iam_role.ecs_instance_role.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly"
}

resource "aws_iam_role_policy_attachment" "ecs_instance_ssm_core" {
  role       = aws_iam_role.ecs_instance_role.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_instance_profile" "ecs" {
  name = "${var.name_prefix}-ecs-instance-profile"
  role = aws_iam_role.ecs_instance_role.name
}

# -----------------------------
# ECS task execution role
# -----------------------------
resource "aws_iam_role" "ecs_task_execution_role" {
  name               = "${var.name_prefix}-ecs-task-exec-role"
  assume_role_policy = data.aws_iam_policy_document.ecs_task_assume.json
  tags               = var.tags
}

resource "aws_iam_role_policy_attachment" "ecs_task_exec" {
  role       = aws_iam_role.ecs_task_execution_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

locals {
  all_bucket_objects_arn = "${var.artifacts_bucket_arn}/*"
}

# -----------------------------
# API task role
# -----------------------------
resource "aws_iam_role" "api_task_role" {
  name               = "${var.name_prefix}-api-task-role"
  assume_role_policy = data.aws_iam_policy_document.ecs_task_assume.json
  tags               = var.tags
}

data "aws_iam_policy_document" "api_task_policy" {
  statement {
    sid = "SendJobsToQueue"
    actions = [
      "sqs:SendMessage",
      "sqs:GetQueueAttributes"
    ]
    resources = [var.sqs_queue_arn]
  }

  statement {
    sid = "ArtifactsReadWrite"
    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:ListBucket",
    ]
    resources = [
      var.artifacts_bucket_arn,
      local.all_bucket_objects_arn,
    ]
  }

  dynamic "statement" {
    for_each = length(var.app_secret_arns) > 0 ? [1] : []
    content {
      sid = "ReadAppSecrets"
      actions = [
        "secretsmanager:GetSecretValue"
      ]
      resources = var.app_secret_arns
    }
  }
}

resource "aws_iam_role_policy" "api_task" {
  role   = aws_iam_role.api_task_role.id
  policy = data.aws_iam_policy_document.api_task_policy.json
}

# ECS Exec channels for API task
data "aws_iam_policy_document" "api_task_exec" {
  statement {
    actions = [
      "ssmmessages:CreateControlChannel",
      "ssmmessages:CreateDataChannel",
      "ssmmessages:OpenControlChannel",
      "ssmmessages:OpenDataChannel",
    ]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "api_task_exec" {
  role   = aws_iam_role.api_task_role.id
  policy = data.aws_iam_policy_document.api_task_exec.json
}

# -----------------------------
# Worker task role
# -----------------------------
resource "aws_iam_role" "worker_task_role" {
  name               = "${var.name_prefix}-worker-task-role"
  assume_role_policy = data.aws_iam_policy_document.ecs_task_assume.json
  tags               = var.tags
}

data "aws_iam_policy_document" "worker_task_policy" {
  statement {
    sid = "ConsumeJobsQueue"
    actions = [
      "sqs:ReceiveMessage",
      "sqs:DeleteMessage",
      "sqs:GetQueueAttributes",
      "sqs:ChangeMessageVisibility",
    ]
    resources = [var.sqs_queue_arn]
  }

  statement {
    sid = "ArtifactsReadWrite"
    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:ListBucket",
    ]
    resources = [
      var.artifacts_bucket_arn,
      local.all_bucket_objects_arn,
    ]
  }

  dynamic "statement" {
    for_each = length(var.app_secret_arns) > 0 ? [1] : []
    content {
      sid = "ReadAppSecrets"
      actions = [
        "secretsmanager:GetSecretValue"
      ]
      resources = var.app_secret_arns
    }
  }

  statement {
    sid = "RunAndWatchBiomedparseTasks"
    actions = [
      "ecs:RunTask",
      "ecs:DescribeTasks",
      "ecs:StopTask",
      "ecs:DescribeTaskDefinition",
      "ecs:DescribeClusters",
    ]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "worker_task" {
  role   = aws_iam_role.worker_task_role.id
  policy = data.aws_iam_policy_document.worker_task_policy.json
}

data "aws_iam_policy_document" "worker_task_exec" {
  statement {
    actions = [
      "ssmmessages:CreateControlChannel",
      "ssmmessages:CreateDataChannel",
      "ssmmessages:OpenControlChannel",
      "ssmmessages:OpenDataChannel",
    ]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "worker_task_exec" {
  role   = aws_iam_role.worker_task_role.id
  policy = data.aws_iam_policy_document.worker_task_exec.json
}

data "aws_iam_policy_document" "worker_run_task" {
  statement {
    actions = ["iam:PassRole"]
    resources = [
      aws_iam_role.worker_task_role.arn,
      aws_iam_role.ecs_task_execution_role.arn,
    ]
    condition {
      test     = "StringEquals"
      variable = "iam:PassedToService"
      values   = ["ecs-tasks.amazonaws.com"]
    }
  }
}

resource "aws_iam_role_policy" "worker_run_task" {
  role   = aws_iam_role.worker_task_role.id
  policy = data.aws_iam_policy_document.worker_run_task.json
}

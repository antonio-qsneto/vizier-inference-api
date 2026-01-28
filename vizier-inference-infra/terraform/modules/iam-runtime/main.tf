
# -----------------------------
# ECS EC2 instance role
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
  name               = "vizier-ecs-instance-role"
  assume_role_policy = data.aws_iam_policy_document.ecs_instance_assume.json
  tags = var.tags
}

resource "aws_iam_role_policy_attachment" "ecs_instance" {
  role       = aws_iam_role.ecs_instance_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonEC2ContainerServiceforEC2Role"
}

resource "aws_iam_role_policy_attachment" "ecr_read" {
  role       = aws_iam_role.ecs_instance_role.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly"
}

resource "aws_iam_role_policy_attachment" "cw_logs" {
  role       = aws_iam_role.ecs_instance_role.name
  policy_arn = "arn:aws:iam::aws:policy/CloudWatchLogsFullAccess"
}

# ECS Exec requires SSM permissions on the container instance (EC2 launch type)
resource "aws_iam_role_policy_attachment" "ssm_core" {
  role       = aws_iam_role.ecs_instance_role.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_instance_profile" "ecs" {
  name = "vizier-ecs-instance-profile"
  role = aws_iam_role.ecs_instance_role.name
}

# -----------------------------
# ECS task execution role
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


resource "aws_iam_role" "ecs_task_execution_role" {
  name               = "vizier-ecs-task-exec-role"
  assume_role_policy = data.aws_iam_policy_document.ecs_task_assume.json
  tags = var.tags
}

resource "aws_iam_role_policy_attachment" "ecs_task_exec" {
  role       = aws_iam_role.ecs_task_execution_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

# -----------------------------
# API task role (SQS send only)
# -----------------------------
resource "aws_iam_role" "api_task_role" {
  name               = "vizier-api-task-role"
  assume_role_policy = data.aws_iam_policy_document.ecs_task_assume.json
  tags = var.tags
}

data "aws_iam_policy_document" "api_task_policy" {
  statement {
    actions   = ["sqs:SendMessage"]
    resources = [var.sqs_queue_arn]
  }
}

resource "aws_iam_role_policy" "api_task" {
  role   = aws_iam_role.api_task_role.id
  policy = data.aws_iam_policy_document.api_task_policy.json
}

# Allow API task to mount/write to EFS via access point IAM auth
data "aws_iam_policy_document" "api_task_efs" {
  statement {
    actions = [
      "elasticfilesystem:ClientMount",
      "elasticfilesystem:ClientWrite"
    ]
    resources = ["arn:aws:elasticfilesystem:*:*:file-system/${var.efs_id}"]
  }
}

resource "aws_iam_role_policy" "api_task_efs" {
  role   = aws_iam_role.api_task_role.id
  policy = data.aws_iam_policy_document.api_task_efs.json
}

# -----------------------------
# Worker task role (SQS consume)
# -----------------------------
resource "aws_iam_role" "worker_task_role" {
  name               = "vizier-worker-task-role"
  assume_role_policy = data.aws_iam_policy_document.ecs_task_assume.json
  tags = var.tags
}

data "aws_iam_policy_document" "worker_task_policy" {
  statement {
    actions = [
      "sqs:ReceiveMessage",
      "sqs:DeleteMessage",
      "sqs:GetQueueAttributes",
      "sqs:ChangeMessageVisibility"
    ]
    resources = [var.sqs_queue_arn]
  }
}

resource "aws_iam_role_policy" "worker_task" {
  role   = aws_iam_role.worker_task_role.id
  policy = data.aws_iam_policy_document.worker_task_policy.json
}

# Allow worker task to mount/write to EFS via access point IAM auth
data "aws_iam_policy_document" "worker_task_efs" {
  statement {
    actions = [
      "elasticfilesystem:ClientMount",
      "elasticfilesystem:ClientWrite"
    ]
    resources = ["arn:aws:elasticfilesystem:*:*:file-system/${var.efs_id}"]
  }
}

# ECS Exec data/control channels from within task (belt-and-suspenders; usually instance role is enough)
data "aws_iam_policy_document" "worker_task_exec" {
  statement {
    actions = [
      "ssmmessages:CreateControlChannel",
      "ssmmessages:CreateDataChannel",
      "ssmmessages:OpenControlChannel",
      "ssmmessages:OpenDataChannel"
    ]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "worker_task_exec" {
  role   = aws_iam_role.worker_task_role.id
  policy = data.aws_iam_policy_document.worker_task_exec.json
}

resource "aws_iam_role_policy" "worker_task_efs" {
  role   = aws_iam_role.worker_task_role.id
  policy = data.aws_iam_policy_document.worker_task_efs.json
}

# Allow worker to launch and monitor BiomedParse tasks
data "aws_iam_policy_document" "worker_run_task" {
  statement {
    actions = [
      "ecs:RunTask",
      "ecs:DescribeTasks",
      "ecs:StopTask"
    ]
    resources = ["*"]
  }

  statement {
    actions   = ["iam:PassRole"]
    resources = [
      aws_iam_role.worker_task_role.arn,
      aws_iam_role.ecs_task_execution_role.arn
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

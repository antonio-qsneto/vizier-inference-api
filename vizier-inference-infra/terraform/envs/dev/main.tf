provider "aws" {
  region = var.aws_region
}

locals {
  tags = {
    Project = "vizier-inference"
    Env     = "dev"
  }
}

# -----------------------------
# Network
# -----------------------------
module "network" {
  source               = "../../modules/network"
  vpc_cidr             = var.vpc_cidr
  enable_nat_gateway   = false
  enable_vpc_endpoints = true
  availability_zone    = var.availability_zone
}

# CloudWatch log groups for ECS services
resource "aws_cloudwatch_log_group" "ecs_api" {
  name              = "/ecs/vizier-api"
  retention_in_days = 14
}

resource "aws_cloudwatch_log_group" "ecs_worker" {
  name              = "/ecs/vizier-worker"
  retention_in_days = 14
}

resource "aws_cloudwatch_log_group" "ecs_biomedparse" {
  name              = "/ecs/vizier-biomedparse"
  retention_in_days = 14
}

# -----------------------------
# DynamoDB (optional for job status)
# Keep only if you're actually using it
# -----------------------------
module "dynamodb" {
  source = "../../modules/dynamodb"
}

# -----------------------------
# API Gateway (optional for now)
# Keep only if you already wired it to the API service/ALB
# -----------------------------
module "api_gateway" {
  source = "../../modules/api-gateway"
}

# -----------------------------
# GitHub OIDC / Terraform deploy role
# -----------------------------
module "iam_github" {
  source        = "../../modules/iam-github"
  github_repo   = "antonio-qsneto/vizier-inference-infra"
  github_branch = "main"
  aws_region    = var.aws_region
}

# -----------------------------
# SQS queue
# -----------------------------
module "sqs" {
  source = "../../modules/sqs"
  name   = "vizier-inference-jobs-dev"
  tags   = local.tags
}

# -----------------------------
# Runtime IAM (ECS + SQS)
# -----------------------------
module "iam_runtime" {
  source        = "../../modules/iam-runtime"
  sqs_queue_arn = module.sqs.queue_arn
  efs_id        = module.efs.efs_id
  tags          = local.tags
}

# -----------------------------
# EFS shared filesystem (NPZ exchange)
# -----------------------------
module "efs" {
  source             = "../../modules/efs"
  vpc_id             = module.network.vpc_id
  private_subnet_ids = [module.network.private_subnet_id]
  ecs_sg_id          = module.network.ecs_security_group_id
  tags               = local.tags
}

# -----------------------------
# GPU ECS cluster (EC2 + ASG + capacity provider)
# + Worker task definition should be created inside this module
# and must mount EFS.
# -----------------------------
module "ecs_gpu" {
  source                 = "../../modules/ecs-gpu"
  cluster_name           = "vizier-dev"
  vpc_id                 = module.network.vpc_id
  private_subnet_ids     = [module.network.private_subnet_id]
  ecs_sg_id              = module.network.ecs_security_group_id
  instance_profile_name  = module.iam_runtime.ecs_instance_profile_name

  instance_type = "g4dn.xlarge"
  asg_min        = 0
  asg_desired    = 0
  asg_max        = 2
  warm_pool_min_size = 0

  # EFS mount info for worker task definition
  efs_id              = module.efs.efs_id
  efs_access_point_id = module.efs.access_point_id

  # Worker roles
  worker_task_execution_role_arn = module.iam_runtime.ecs_task_execution_role_arn
  worker_task_role_arn           = module.iam_runtime.worker_task_role_arn

  # Images (set these variables in terraform.tfvars)
  worker_image = var.worker_image
  biomedparse_image = var.biomedparse_image

  sqs_queue_url = module.sqs.queue_url
  aws_region    = var.aws_region

  tags = local.tags
}

# -----------------------------
# API ECS task/service (CPU) - mounts EFS
# This is what your empty modules/ecs should become.
# -----------------------------
module "ecs" {
  source = "../../modules/ecs"

  # Deploy API into the SAME cluster created above
  cluster_name = module.ecs_gpu.cluster_name
  cpu_capacity_provider_name = module.ecs_gpu.cpu_capacity_provider_name

  subnet_ids        = [module.network.private_subnet_id]
  security_group_id = module.network.ecs_security_group_id

  # Roles
  execution_role_arn = module.iam_runtime.ecs_task_execution_role_arn
  task_role_arn      = module.iam_runtime.api_task_role_arn

  # EFS mount info
  efs_id              = module.efs.efs_id
  efs_access_point_id = module.efs.access_point_id

  # Image
  container_image = var.api_image

  # Queue/env
  sqs_queue_url = module.sqs.queue_url
  aws_region    = var.aws_region

  tags = local.tags
}

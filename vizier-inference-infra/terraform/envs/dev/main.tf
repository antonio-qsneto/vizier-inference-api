provider "aws" {
  region = var.aws_region
}

data "aws_caller_identity" "current" {}

locals {
  tags = {
    Project = var.project_name
    Env     = var.environment
  }

  resolved_artifacts_bucket_name = coalesce(
    var.s3_artifacts_bucket_name,
    lower("${var.project_name}-${var.environment}-${data.aws_caller_identity.current.account_id}-artifacts")
  )
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
# Persistent job state
# -----------------------------
module "dynamodb" {
  source = "../../modules/dynamodb"

  table_name  = var.jobs_table_name
  kms_key_arn = var.dynamodb_kms_key_arn
  tags        = local.tags
}

# -----------------------------
# Persistent job artifacts
# -----------------------------
module "s3" {
  source = "../../modules/s3"

  bucket_name = local.resolved_artifacts_bucket_name
  kms_key_arn = var.s3_kms_key_arn
  tags        = local.tags
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
# SQS queue + DLQ
# -----------------------------
module "sqs" {
  source = "../../modules/sqs"

  name     = var.jobs_queue_name
  dlq_name = var.jobs_dlq_name
  tags     = local.tags
}

# -----------------------------
# Runtime IAM (ECS + SQS + S3 + DynamoDB)
# -----------------------------
module "iam_runtime" {
  source = "../../modules/iam-runtime"

  sqs_queue_arn        = module.sqs.queue_arn
  jobs_table_arn       = module.dynamodb.table_arn
  artifacts_bucket_arn = module.s3.bucket_arn
  job_artifacts_prefix = var.job_artifacts_prefix

  tags = local.tags
}

# -----------------------------
# GPU ECS cluster (EC2 + ASG + capacity provider)
# + Worker task definition inside this module
# -----------------------------
module "ecs_gpu" {
  source                = "../../modules/ecs-gpu"
  cluster_name          = "vizier-dev"
  vpc_id                = module.network.vpc_id
  private_subnet_ids    = [module.network.private_subnet_id]
  ecs_sg_id             = module.network.ecs_security_group_id
  instance_profile_name = module.iam_runtime.ecs_instance_profile_name

  gpu_ami_id    = var.gpu_ami_id
  instance_type = "g4dn.xlarge"
  asg_min       = 1
  asg_desired   = 1
  asg_max       = 1

  worker_task_execution_role_arn = module.iam_runtime.ecs_task_execution_role_arn
  worker_task_role_arn           = module.iam_runtime.worker_task_role_arn

  worker_image      = var.worker_image
  biomedparse_image = var.biomedparse_image

  sqs_queue_url    = module.sqs.queue_url
  jobs_table_name  = module.dynamodb.table_name
  artifacts_bucket = module.s3.bucket_name
  aws_region       = var.aws_region

  tags = local.tags
}

# -----------------------------
# API ECS task/service (CPU)
# -----------------------------
module "ecs" {
  source = "../../modules/ecs"

  cluster_name               = module.ecs_gpu.cluster_name
  cpu_capacity_provider_name = module.ecs_gpu.cpu_capacity_provider_name

  vpc_id            = module.network.vpc_id
  subnet_ids        = [module.network.private_subnet_id]
  security_group_id = module.network.ecs_security_group_id

  execution_role_arn = module.iam_runtime.ecs_task_execution_role_arn
  task_role_arn      = module.iam_runtime.api_task_role_arn

  container_image = var.api_image

  sqs_queue_url        = module.sqs.queue_url
  jobs_table_name      = module.dynamodb.table_name
  artifacts_bucket     = module.s3.bucket_name
  job_artifacts_prefix = var.job_artifacts_prefix
  aws_region           = var.aws_region

  service_discovery_namespace_name = "internal"
  service_discovery_service_name   = "api"

  tags = local.tags
}

module "cognito" {
  source = "../../modules/cognito"

  project_name      = var.project_name
  environment       = var.environment
  callback_urls     = var.cognito_callback_urls
  logout_urls       = var.cognito_logout_urls
  mfa_configuration = var.cognito_mfa_configuration
  ses_source_arn    = var.cognito_ses_source_arn
  tags              = local.tags
}

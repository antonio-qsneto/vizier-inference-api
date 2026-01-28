resource "aws_vpc" "this" {
  cidr_block           = var.vpc_cidr
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = {
    Name = "vizier-vpc"
  }
}

resource "aws_internet_gateway" "this" {
  vpc_id = aws_vpc.this.id

  tags = {
    Name = "vizier-igw"
  }
}

resource "aws_subnet" "public" {
  vpc_id                  = aws_vpc.this.id
  cidr_block              = var.public_subnet_cidr
  availability_zone       = var.availability_zone
  map_public_ip_on_launch = true

  tags = {
    Name = "vizier-public"
  }
}

resource "aws_subnet" "private" {
  vpc_id            = aws_vpc.this.id
  cidr_block        = var.private_subnet_cidr
  availability_zone = var.availability_zone

  tags = {
    Name = "vizier-private"
  }
}

resource "aws_eip" "nat" {
  count  = var.enable_nat_gateway ? 1 : 0
  domain = "vpc"
}

resource "aws_nat_gateway" "this" {
  count         = var.enable_nat_gateway ? 1 : 0
  allocation_id = aws_eip.nat[0].id
  subnet_id     = aws_subnet.public.id

  tags = {
    Name = "vizier-nat"
  }

  depends_on = [aws_internet_gateway.this]
}


resource "aws_route_table" "public" {
  vpc_id = aws_vpc.this.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.this.id
  }

  tags = {
    Name = "vizier-public-rt"
  }
}

resource "aws_route_table_association" "public" {
  subnet_id      = aws_subnet.public.id
  route_table_id = aws_route_table.public.id
}

resource "aws_route_table" "private" {
  vpc_id = aws_vpc.this.id

  dynamic "route" {
    for_each = var.enable_nat_gateway ? [1] : []
    content {
      cidr_block     = "0.0.0.0/0"
      nat_gateway_id = aws_nat_gateway.this[0].id
    }
  }

  tags = {
    Name = "vizier-private-rt"
  }
}


resource "aws_route_table_association" "private" {
  subnet_id      = aws_subnet.private.id
  route_table_id = aws_route_table.private.id
}

resource "aws_security_group" "ecs" {
  name        = "vizier-ecs-sg"
  description = "Security group for ECS GPU instances"
  vpc_id      = aws_vpc.this.id

  ingress {
    description = "Internal traffic"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = [var.vpc_cidr]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "vizier-ecs-sg"
  }
}

data "aws_region" "current" {}

resource "aws_vpc_endpoint" "s3" {
  count             = var.enable_vpc_endpoints ? 1 : 0
  vpc_id            = aws_vpc.this.id
  service_name = "com.amazonaws.${data.aws_region.current.region}.s3"
  vpc_endpoint_type = "Gateway"

  route_table_ids = [
    aws_route_table.private.id
  ]

  tags = {
    Name = "vizier-s3-endpoint"
  }
}

resource "aws_vpc_endpoint" "dynamodb" {
  count             = var.enable_vpc_endpoints ? 1 : 0
  vpc_id            = aws_vpc.this.id
  service_name      = "com.amazonaws.${data.aws_region.current.region}.dynamodb"
  vpc_endpoint_type = "Gateway"

  route_table_ids = [
    aws_route_table.private.id
  ]

  tags = {
    Name = "vizier-dynamodb-endpoint"
  }
}

resource "aws_security_group" "endpoints" {
  name        = "vizier-vpce-sg"
  description = "Allow HTTPS from VPC to interface endpoints"
  vpc_id      = aws_vpc.this.id

  ingress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = [var.vpc_cidr]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "vizier-vpce-sg"
  }
}

locals {
  # Interface endpoints needed when private subnet has no NAT:
  # - ecs, ec2: ECS agent registration and instance metadata calls
  # - ecs-telemetry, ecs-agent: ECS agent telemetry/data plane
  # - ecr.api, ecr.dkr: pull images
  # - logs: CloudWatch Logs
  # - sqs, sts: queue access and IAM auth
  # - ssm, ec2messages, ssmmessages: ECS Exec (execute-command)
  interface_endpoints = var.enable_vpc_endpoints ? toset([
    "ecs",
    "ecs-telemetry",
    "ecs-agent",
    "ec2",
    "ecr.api",
    "ecr.dkr",
    "logs",
    "sqs",
    "sts",
    "ssm",
    "ec2messages",
    "ssmmessages"
  ]) : toset([])
}


resource "aws_vpc_endpoint" "interface" {
  for_each          = local.interface_endpoints
  vpc_id            = aws_vpc.this.id
  vpc_endpoint_type = "Interface"
  service_name      = "com.amazonaws.${data.aws_region.current.region}.${each.key}"

  subnet_ids         = [aws_subnet.private.id]
  security_group_ids = [aws_security_group.endpoints.id]
  private_dns_enabled = true

  tags = {
    Name = "vizier-${each.key}-endpoint"
  }
}

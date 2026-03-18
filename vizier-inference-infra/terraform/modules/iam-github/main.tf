data "tls_certificate" "github_actions" {
  url = "https://token.actions.githubusercontent.com"
}

locals {
  github_subjects = concat(
    ["repo:${var.github_repo}:ref:refs/heads/${var.github_branch}"],
    [for env_name in var.github_environments : "repo:${var.github_repo}:environment:${env_name}"],
  )
}

resource "aws_iam_openid_connect_provider" "github" {
  url             = "https://token.actions.githubusercontent.com"
  client_id_list  = ["sts.amazonaws.com"]
  thumbprint_list = [data.tls_certificate.github_actions.certificates[0].sha1_fingerprint]
}

data "aws_iam_policy_document" "github_oidc_trust" {
  statement {
    effect = "Allow"
    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.github.arn]
    }
    actions = ["sts:AssumeRoleWithWebIdentity"]

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }

    condition {
      test     = "StringLike"
      variable = "token.actions.githubusercontent.com:sub"
      values   = local.github_subjects
    }
  }
}

resource "aws_iam_role" "github_actions_terraform" {
  name               = "github-actions-terraform"
  assume_role_policy = data.aws_iam_policy_document.github_oidc_trust.json
}

data "aws_iam_policy_document" "terraform_permissions" {
  statement {
    effect = "Allow"
    actions = [
      "ec2:*",
      "ecs:*",
      "iam:*",
      "sqs:*",
      "logs:*",
      "ecr:*",
      "elasticloadbalancing:*",
      "autoscaling:*",
      "cloudwatch:*",
      "rds:*",
      "s3:*",
      "dynamodb:*",
      "secretsmanager:*",
      "kms:*",
      "cognito-idp:*",
      "acm:*",
      "route53:*",
      "amplify:*",
      "cloudfront:*",
      "ssm:*",
      "sts:GetCallerIdentity"
    ]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "terraform" {
  role   = aws_iam_role.github_actions_terraform.id
  policy = data.aws_iam_policy_document.terraform_permissions.json
}

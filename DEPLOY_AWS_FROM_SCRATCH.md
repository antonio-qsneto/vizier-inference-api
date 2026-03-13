# Deploy AWS Do Zero (Passo a Passo Completo)

Este guia segue a ordem lógica correta para subir o projeto com:
- Frontend no Amplify
- Django API + worker em ECS/Fargate
- BiomedParse em ECS EC2 GPU
- RDS PostgreSQL + S3 + SQS + Secrets Manager
- CI/CD via GitHub Actions com OIDC

## 0. Pré-requisitos

Você precisa ter instalado:
- `aws` CLI v2
- `terraform` >= 1.5
- `gh` (GitHub CLI)
- `jq`
- `openssl`

E ter:
- Permissão AWS para criar IAM, ECS, EC2, RDS, S3, SQS, Cognito, Secrets Manager.
- Permissão admin no repositório GitHub.

No terminal:

```bash
cd /home/antonio/medIA/development/vizier-inference-api

export AWS_REGION=us-east-1
export GH_REPO="antonio-qsneto/vizier-inference-api"

aws sts get-caller-identity
gh auth status || gh auth login --web
gh repo set-default "$GH_REPO"
```

## 1. Criar backend remoto do Terraform (state e lock)

### 1.1 Criar bucket S3 do state

```bash
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
export TF_STATE_BUCKET="vizier-terraform-state-${ACCOUNT_ID}-${AWS_REGION}"
export TF_STATE_LOCK_TABLE="terraform-locks"

if ! aws s3api head-bucket --bucket "$TF_STATE_BUCKET" 2>/dev/null; then
  if [ "$AWS_REGION" = "us-east-1" ]; then
    aws s3api create-bucket --bucket "$TF_STATE_BUCKET"
  else
    aws s3api create-bucket \
      --bucket "$TF_STATE_BUCKET" \
      --create-bucket-configuration LocationConstraint="$AWS_REGION"
  fi
fi

aws s3api put-bucket-versioning \
  --bucket "$TF_STATE_BUCKET" \
  --versioning-configuration Status=Enabled

aws s3api put-bucket-encryption \
  --bucket "$TF_STATE_BUCKET" \
  --server-side-encryption-configuration '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"}}]}'
```

### 1.2 Criar lock table (DynamoDB)

```bash
if ! aws dynamodb describe-table --table-name "$TF_STATE_LOCK_TABLE" >/dev/null 2>&1; then
  aws dynamodb create-table \
    --table-name "$TF_STATE_LOCK_TABLE" \
    --attribute-definitions AttributeName=LockID,AttributeType=S \
    --key-schema AttributeName=LockID,KeyType=HASH \
    --billing-mode PAY_PER_REQUEST
fi
```

### 1.3 Criar `backend.hcl` (dev/prod)

```bash
cat > vizier-inference-infra/terraform/envs/dev/backend.hcl <<EOF
bucket         = "${TF_STATE_BUCKET}"
key            = "envs/dev/terraform.tfstate"
region         = "${AWS_REGION}"
dynamodb_table = "${TF_STATE_LOCK_TABLE}"
encrypt        = true
EOF

cat > vizier-inference-infra/terraform/envs/prod/backend.hcl <<EOF
bucket         = "${TF_STATE_BUCKET}"
key            = "envs/prod/terraform.tfstate"
region         = "${AWS_REGION}"
dynamodb_table = "${TF_STATE_LOCK_TABLE}"
encrypt        = true
EOF
```

## 2. Bootstrap inicial da role OIDC (antes de usar GitHub Actions)

Objetivo: criar `AWS_ROLE_ARN` que o GitHub Actions vai assumir.

```bash
cd vizier-inference-infra/terraform/envs/dev

terraform init -backend-config=backend.hcl -reconfigure

terraform apply -auto-approve \
  -target=module.iam_github \
  -var="github_repo=${GH_REPO}" \
  -var="aws_region=${AWS_REGION}" \
  -var="rds_password=dummy-not-used" \
  -var="django_secret_key=dummy-not-used" \
  -var="inference_api_bearer_token=dummy-not-used"

export AWS_ROLE_ARN="$(terraform output -raw github_actions_role_arn)"
cd /home/antonio/medIA/development/vizier-inference-api
```

Se aparecer warning de variável não declarada (`api_image`, `worker_image`, `biomedparse_image`), limpe o arquivo local `vizier-inference-infra/terraform/envs/dev/terraform.tfvars` removendo essas chaves legadas.

## 3. Gerar valores de secrets (dev/prod)

```bash
export RDS_PASSWORD_DEV="$(openssl rand -base64 24 | tr -d '\n' | tr '/+' '_-')"
export DJANGO_SECRET_KEY_DEV="$(openssl rand -base64 64 | tr -d '\n')"
export API_BEARER_DEV="$(openssl rand -hex 32)"

export RDS_PASSWORD_PROD="$(openssl rand -base64 24 | tr -d '\n' | tr '/+' '_-')"
export DJANGO_SECRET_KEY_PROD="$(openssl rand -base64 64 | tr -d '\n')"
export API_BEARER_PROD="$(openssl rand -hex 32)"
```

## 4. Definir imagem BiomedParse existente no ECR

Como o BiomedParse já existe no seu ECR, informe a URI completa:

```bash
export BIOMEDPARSE_IMAGE_OVERRIDE="996561439065.dkr.ecr.${AWS_REGION}.amazonaws.com/biomedparse:latest"
```

Observação: os workflows já têm fallback para essa imagem caso a variável não seja definida.

## 5. Criar GitHub Environments e preencher secrets/variables

### 5.1 Criar environments

```bash
gh api --method PUT "repos/${GH_REPO}/environments/development" >/dev/null
gh api --method PUT "repos/${GH_REPO}/environments/production" >/dev/null
```

### 5.2 Preencher `development`

```bash
gh secret set AWS_ROLE_ARN --repo "$GH_REPO" --env development --body "$AWS_ROLE_ARN"
gh secret set TF_VAR_RDS_PASSWORD --repo "$GH_REPO" --env development --body "$RDS_PASSWORD_DEV"
gh secret set TF_VAR_DJANGO_SECRET_KEY --repo "$GH_REPO" --env development --body "$DJANGO_SECRET_KEY_DEV"
gh secret set TF_VAR_INFERENCE_API_BEARER_TOKEN --repo "$GH_REPO" --env development --body "$API_BEARER_DEV"
# opcional:
# gh secret set SMOKE_AUTH_TOKEN --repo "$GH_REPO" --env development --body "<jwt-valido>"

gh variable set AWS_REGION --repo "$GH_REPO" --env development --body "$AWS_REGION"
gh variable set TF_STATE_BUCKET --repo "$GH_REPO" --env development --body "$TF_STATE_BUCKET"
gh variable set TF_STATE_LOCK_TABLE --repo "$GH_REPO" --env development --body "$TF_STATE_LOCK_TABLE"
gh variable set BIOMEDPARSE_IMAGE_OVERRIDE --repo "$GH_REPO" --env development --body "$BIOMEDPARSE_IMAGE_OVERRIDE"
# opcional:
# gh variable set BOOTSTRAP_ADMIN_EMAIL --repo "$GH_REPO" --env development --body "admin@empresa.com"
```

### 5.3 Preencher `production`

```bash
gh secret set AWS_ROLE_ARN --repo "$GH_REPO" --env production --body "$AWS_ROLE_ARN"
gh secret set TF_VAR_RDS_PASSWORD --repo "$GH_REPO" --env production --body "$RDS_PASSWORD_PROD"
gh secret set TF_VAR_DJANGO_SECRET_KEY --repo "$GH_REPO" --env production --body "$DJANGO_SECRET_KEY_PROD"
gh secret set TF_VAR_INFERENCE_API_BEARER_TOKEN --repo "$GH_REPO" --env production --body "$API_BEARER_PROD"
# opcional:
# gh secret set SMOKE_AUTH_TOKEN --repo "$GH_REPO" --env production --body "<jwt-valido>"

gh variable set AWS_REGION --repo "$GH_REPO" --env production --body "$AWS_REGION"
gh variable set TF_STATE_BUCKET --repo "$GH_REPO" --env production --body "$TF_STATE_BUCKET"
gh variable set TF_STATE_LOCK_TABLE --repo "$GH_REPO" --env production --body "$TF_STATE_LOCK_TABLE"
gh variable set BIOMEDPARSE_IMAGE_OVERRIDE --repo "$GH_REPO" --env production --body "$BIOMEDPARSE_IMAGE_OVERRIDE"
# opcional:
# gh variable set BOOTSTRAP_ADMIN_EMAIL --repo "$GH_REPO" --env production --body "admin@empresa.com"
```

## 6. Primeiro deploy DEV

Você pode disparar com push na `main` ou manual:

```bash
gh workflow run deploy-dev.yml --repo "$GH_REPO" --ref main
gh run watch --repo "$GH_REPO"
```

Esse workflow já:
1. garante ECR
2. build/push do backend
3. `terraform apply` completo em dev
4. migration automática (ECS one-off task)
5. bootstrap opcional
6. smoke test

## 7. Obter endpoint da API dev (ALB) e configurar Amplify

```bash
cd vizier-inference-infra/terraform/envs/dev
terraform init -backend-config=backend.hcl -reconfigure
DEV_ALB_DNS="$(terraform output -raw alb_dns_name)"
echo "$DEV_ALB_DNS"
cd /home/antonio/medIA/development/vizier-inference-api
```

No Amplify (ambiente dev), preencher:
- `VITE_API_BASE_URL=http://<DEV_ALB_DNS>`
- `VITE_USE_ASYNC_S3_UPLOAD=true`
- `VITE_COGNITO_*` (region, pool id, client id, domain, redirect/logout)

## 8. Validação funcional mínima (dev)

1. Health:
```bash
API_BASE_URL="http://<DEV_ALB_DNS>" ./scripts/deploy/smoke_api.sh
```

2. E2E de negócio:
- criar job
- upload direto S3
- `upload-complete`
- verificar transição `QUEUED/RUNNING/COMPLETED`
- baixar outputs via presigned GET

## 9. Deploy de produção (manual)

Escolha a tag de imagem validada em dev (normalmente SHA do commit):

```bash
IMAGE_TAG="<sha-validado-em-dev>"
SOURCE_COMMIT_SHA="<sha-com-ci-success>"
gh workflow run deploy-prod.yml --repo "$GH_REPO" --ref main \
  -f image_tag="$IMAGE_TAG" \
  -f source_commit_sha="$SOURCE_COMMIT_SHA"
gh run watch --repo "$GH_REPO"
```

Depois configure no Amplify prod:
- `VITE_API_BASE_URL=http://<PROD_ALB_DNS>`
- `VITE_USE_ASYNC_S3_UPLOAD=true`
- `VITE_COGNITO_*` do ambiente prod

## 10. Operação pós-go-live

### Reexecutar migrations manualmente (se necessário)
Use:
- [run_ecs_migrate.sh](/home/antonio/medIA/development/vizier-inference-api/scripts/deploy/run_ecs_migrate.sh)

### Bootstrap de admin/tenant manual
Use:
- [run_bootstrap.sh](/home/antonio/medIA/development/vizier-inference-api/scripts/deploy/run_bootstrap.sh)

### Promover tag sem rebuild
Use:
- [tag_release.sh](/home/antonio/medIA/development/vizier-inference-api/scripts/deploy/tag_release.sh)

## 11. Rollback

1. Identifique tag anterior estável no ECR.
2. Rode `deploy-prod.yml` novamente com `image_tag=<tag-anterior>` e `source_commit_sha=<sha-com-ci-success>`.
3. Verifique health + alarmes + processamento de jobs.

## 12. Erros comuns

1. `terraform init` falha com lock:
- conferir `TF_STATE_LOCK_TABLE` e permissão DynamoDB na role.

2. Workflow falha em assumir role:
- conferir `AWS_ROLE_ARN` no environment correto.
- conferir trust policy OIDC (`repo`, branch e environment).

3. Worker não processa jobs:
- conferir `INFERENCE_JOBS_QUEUE_URL`, `BIO_ECS_*` e imagem BiomedParse.

4. Task GPU não sobe:
- conferir capacidade da ASG GPU e AMI compatível ECS GPU.

5. Frontend sem resposta:
- conferir `VITE_API_BASE_URL` no Amplify e CORS no backend/S3.

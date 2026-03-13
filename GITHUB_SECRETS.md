# GitHub Secrets/Variables Matrix

## Environments
Criar dois GitHub Environments:
- `development`
- `production`

## Secrets obrigatórios (por environment)
1. `AWS_ROLE_ARN`
2. `TF_VAR_RDS_PASSWORD`
3. `TF_VAR_DJANGO_SECRET_KEY`

## Secrets opcionais (por environment)
1. `TF_VAR_INFERENCE_API_BEARER_TOKEN`
2. `SMOKE_AUTH_TOKEN`

## Variables obrigatórias (por environment)
1. `AWS_REGION` (ex.: `us-east-1`)
2. `TF_STATE_BUCKET` (bucket do state terraform)

## Variables opcionais (por environment)
1. `TF_STATE_LOCK_TABLE` (se usar lock table)
2. `BOOTSTRAP_ADMIN_EMAIL` (para bootstrap automático)
3. `BIOMEDPARSE_IMAGE_OVERRIDE` (se quiser forçar outra imagem)
4. `BACKEND_ECR_REPOSITORY_URL` (recomendado quando ECR é manual)
5. `BIOMEDPARSE_ECR_REPOSITORY_URL` (recomendado quando ECR é manual)
6. `MANAGE_BACKEND_ECR_REPOSITORY` (`false` para não gerenciar via Terraform)
7. `MANAGE_BIOMEDPARSE_ECR_REPOSITORY` (`false` para não gerenciar via Terraform)

Valor recomendado no seu cenário:
- `996561439065.dkr.ecr.us-east-1.amazonaws.com/biomedparse:latest`

Valores recomendados no seu cenário:
- `BACKEND_ECR_REPOSITORY_URL=996561439065.dkr.ecr.us-east-1.amazonaws.com/vizier-backend-dev` (dev)
- `BIOMEDPARSE_ECR_REPOSITORY_URL=996561439065.dkr.ecr.us-east-1.amazonaws.com/biomedparse`
- `MANAGE_BACKEND_ECR_REPOSITORY=false`
- `MANAGE_BIOMEDPARSE_ECR_REPOSITORY=false`

## Variáveis Terraform recomendadas
Estas podem ficar em `terraform.tfvars` ou virar `TF_VAR_*` no environment.
1. `backend_image_tag`
2. `biomedparse_image_tag`
3. `frontend_upload_allowed_origins`
4. `alb_ingress_cidrs`
5. `gpu_*` (janela e capacidade)

## Convenção usada nos workflows
Os workflows mapeiam secrets GitHub em variáveis Terraform assim:
- `TF_VAR_RDS_PASSWORD` -> `TF_VAR_rds_password`
- `TF_VAR_DJANGO_SECRET_KEY` -> `TF_VAR_django_secret_key`
- `TF_VAR_INFERENCE_API_BEARER_TOKEN` -> `TF_VAR_inference_api_bearer_token`

## Amplify (frontend)
No Amplify App, configurar por branch/ambiente:
1. `VITE_API_BASE_URL` (`http://<alb-dns>` dev/prod)
2. `VITE_USE_ASYNC_S3_UPLOAD=true`
3. Variáveis Cognito:
   - `VITE_COGNITO_REGION`
   - `VITE_COGNITO_USER_POOL_ID`
   - `VITE_COGNITO_CLIENT_ID`
   - `VITE_COGNITO_DOMAIN`
   - `VITE_COGNITO_REDIRECT_URI`
   - `VITE_COGNITO_LOGOUT_URI`

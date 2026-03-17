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
3. `TF_VAR_STRIPE_SECRET_KEY`
4. `TF_VAR_STRIPE_WEBHOOK_SECRET`

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
8. `AMPLIFY_SYNC_ENABLED` (`true` para sincronizar variáveis VITE automaticamente no deploy)
9. `AMPLIFY_APP_ID` (App ID do Amplify)
10. `AMPLIFY_BRANCH` (ex.: `main`)
11. `AMPLIFY_FRONTEND_BASE_URL` (ex.: `https://viziermed.com`)
12. `AMPLIFY_API_SCHEME` (`http` ou `https`)
13. `TF_VAR_COGNITO_CALLBACK_URLS` (opcional, JSON array string para Terraform)
14. `TF_VAR_COGNITO_LOGOUT_URLS` (opcional, JSON array string para Terraform)
15. `TF_VAR_ENABLE_NAT_GATEWAY` (`true` recomendado para Stripe + Cognito hosted endpoints)
16. `TF_VAR_ENABLE_VPC_ENDPOINTS` (`false` recomendado quando NAT está ativo para reduzir custo PrivateLink)
17. `TF_VAR_ENABLE_STRIPE_BILLING` (`true` para liberar endpoints de billing)
18. `TF_VAR_STRIPE_PRODUCT_ID` (opcional)
19. `TF_VAR_STRIPE_PRICE_ID_INDIVIDUAL_MONTHLY` (opcional)
20. `TF_VAR_STRIPE_PRICE_ID_INDIVIDUAL_ANNUAL` (opcional)
21. `TF_VAR_STRIPE_PRICE_LOOKUP_KEY_INDIVIDUAL_MONTHLY` (opcional)
22. `TF_VAR_STRIPE_PRICE_LOOKUP_KEY_INDIVIDUAL_ANNUAL` (opcional)
23. `TF_VAR_STRIPE_ALLOWED_REDIRECT_ORIGINS` (JSON array string opcional; ex.: `["https://viziermed.com"]`)

Valor recomendado no seu cenário:
- `996561439065.dkr.ecr.us-east-1.amazonaws.com/biomedparse:v2-20260317-131652-e02096c`
- `996561439065.dkr.ecr.us-east-1.amazonaws.com/biomedparse@sha256:b61afa1fb0a1abb04ce41d575848e35763ad62d9471244bb349be1d8a3952ae0`

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
1. `VITE_API_BASE_URL` (`https://<api-cloudfront-domain>` preferencial em frontend HTTPS)
2. `VITE_BILLING_CHECKOUT_ENDPOINT` (`<VITE_API_BASE_URL>/api/auth/billing/checkout/`)
3. `VITE_BILLING_PORTAL_ENDPOINT` (`<VITE_API_BASE_URL>/api/auth/billing/portal/`)
4. `VITE_USE_ASYNC_S3_UPLOAD=true`
5. Variáveis Cognito:
   - `VITE_COGNITO_REGION`
   - `VITE_COGNITO_USER_POOL_ID`
   - `VITE_COGNITO_CLIENT_ID`
   - `VITE_COGNITO_DOMAIN`
   - `VITE_COGNITO_REDIRECT_URI`
   - `VITE_COGNITO_LOGOUT_URI`

Automação opcional:
- Se `AMPLIFY_SYNC_ENABLED=true`, os workflows `deploy-dev` e `deploy-prod` atualizam essas variáveis automaticamente via `aws amplify update-branch`.
- Para evitar chaves duplicadas no console do Amplify, o script remove as `VITE_*` gerenciadas (incluindo billing checkout/portal) do nível global do App e mantém no nível do Branch.
- Os workflows também montam `cognito_callback/logout` automaticamente usando `AMPLIFY_FRONTEND_BASE_URL`; `TF_VAR_COGNITO_*` só é necessário para override.
- O fluxo atual usa `api_cloudfront_domain_name` (HTTPS) quando disponível para evitar mixed content.
- Se frontend estiver em HTTPS e backend no ALB HTTP sem CloudFront, o script tenta modo proxy no Amplify, mas o target HTTP pode ser bloqueado pelo próprio Amplify.
- O script também mantém a regra SPA de fallback para `/index.html`, evitando `404` em `/auth/callback`.

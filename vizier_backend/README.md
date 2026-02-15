# Vizier Med - Backend SaaS

Aplicação backend Django para processamento de imagens médicas (DICOM) com segmentação assistida por IA, seguindo as melhores práticas SaaS 2025/2026 e AWS.

## Características

- **Autenticação AWS Cognito**: Integração segura com JWT
- **Multi-tenancy**: Suporte a múltiplas clínicas com isolamento de dados
- **Pipeline DICOM**: Conversão automática ZIP → DICOM → NPZ
- **Inferência Assíncrona**: Submissão de jobs a API externa com polling
- **Armazenamento S3**: Resultados em NIfTI (.nii.gz) com URLs assinadas
- **Audit Logging**: Conformidade LGPD com rastreamento completo
- **API RESTful**: Django REST Framework com documentação Swagger
- **Containerização**: Docker e docker-compose para desenvolvimento
- **CI/CD**: GitHub Actions para testes e deploy automático

## Requisitos

- Python 3.11+
- PostgreSQL 15+
- Redis 7+
- Docker e Docker Compose (opcional)
- AWS Cognito, S3, RDS (produção)

## Instalação Local

### 1. Clonar repositório

```bash
git clone <repository-url>
cd vizier_backend
```

### 2. Criar ambiente virtual

```bash
python3.11 -m venv venv
source venv/bin/activate  # Linux/Mac
# ou
venv\Scripts\activate  # Windows
```

### 3. Instalar dependências

```bash
pip install -r requirements.txt
```

### 4. Configurar variáveis de ambiente

```bash
cp .env.example .env
# Editar .env com suas credenciais
```

### 5. Executar migrations

```bash
python manage.py migrate
```

### 6. Criar superusuário (opcional)

```bash
python manage.py createsuperuser
```

### 7. Executar servidor de desenvolvimento

```bash
python manage.py runserver
```

Acesse: http://localhost:8000/api/health/

## Execução com Docker

### 1. Build e start dos serviços

```bash
docker-compose up -d
```

### 2. Executar migrations

```bash
docker-compose exec web python manage.py migrate
```

### 3. Acessar aplicação

- API: http://localhost:8000
- Banco de dados: localhost:5432
- Redis: localhost:6379

## Estrutura do Projeto

```
vizier_backend/
├── apps/
│   ├── accounts/          # Autenticação e usuários
│   ├── tenants/           # Clínicas e multi-tenancy
│   ├── studies/           # Estudos DICOM
│   ├── inference/         # Integração com API de inferência
│   ├── audit/             # Audit logging
│   └── health/            # Health checks
├── services/              # Serviços de negócio
│   ├── dicom_pipeline.py  # Conversão DICOM → NPZ
│   ├── s3_utils.py        # Utilitários S3
│   └── nifti_converter.py # Conversão NPZ → NIfTI
├── vizier_backend/        # Configurações Django
├── data/                  # Dados estáticos (categorias)
├── Dockerfile             # Imagem Docker
├── docker-compose.yml     # Orquestração de serviços
├── serverless.yml         # Configuração AWS Lambda
└── requirements.txt       # Dependências Python
```

## Endpoints da API

### Health Check
- `GET /api/health/` - Status da aplicação

### Autenticação
- `GET /api/auth/users/` - Listar usuários
- `GET /api/auth/users/me/` - Perfil do usuário autenticado
- `GET /api/auth/categories/` - Listar categorias de segmentação

### Clínicas
- `GET /api/clinics/clinics/` - Listar clínicas
- `POST /api/clinics/clinics/invite/` - Convidar médico
- `GET /api/clinics/clinics/doctors/` - Listar médicos
- `DELETE /api/clinics/clinics/remove_doctor/` - Remover médico

### Estudos
- `POST /api/studies/` - Criar novo estudo (upload DICOM ZIP)
- `GET /api/studies/{id}/` - Detalhes do estudo
- `GET /api/studies/{id}/status/` - Status e progresso
- `GET /api/studies/{id}/result/` - URLs assinadas dos NIfTI (imagem + máscara) para overlay no frontend
- `GET /api/studies/{id}/visualization/` - Alias do endpoint acima

## Variáveis de Ambiente

```env
# Django
DEBUG=False
SECRET_KEY=your-secret-key
ALLOWED_HOSTS=localhost,127.0.0.1

# Database
DATABASE_URL=postgresql://user:password@localhost:5432/vizier_med

# AWS
AWS_REGION=us-east-1
AWS_ACCESS_KEY_ID=your-access-key
AWS_SECRET_ACCESS_KEY=your-secret-key
S3_BUCKET=vizier-med-bucket

# AWS Cognito
COGNITO_REGION=us-east-1
COGNITO_USER_POOL_ID=us-east-1_xxxxxxxxx
COGNITO_CLIENT_ID=your-client-id

# Inference API
INFERENCE_API_URL=http://inference-api:8001
INFERENCE_API_TIMEOUT=300

# DICOM Processing
DICOM_TARGET_HW=(512, 512)
DICOM_TARGET_SLICES=64
DICOM_WINDOW_CENTER=40
DICOM_WINDOW_WIDTH=400

# Redis
REDIS_URL=redis://localhost:6379/0

# Features
ENABLE_SEAT_LIMIT_CHECK=True
```

## Testes

### Executar todos os testes

```bash
python manage.py test
```

### Executar testes de um app específico

```bash
python manage.py test apps.accounts.tests
```

### Executar com cobertura

```bash
pip install coverage
coverage run --source='.' manage.py test
coverage report
coverage html
```

## Linting e Formatação

```bash
# Verificar estilo
flake8 apps/ vizier_backend/ services/ --max-line-length=120

# Formatar código
black apps/ vizier_backend/ services/

# Organizar imports
isort apps/ vizier_backend/ services/
```

## Deploy em Produção

### AWS ECS

```bash
# Build imagem Docker
docker build -t vizier-med-backend:latest .

# Push para ECR
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin <account-id>.dkr.ecr.us-east-1.amazonaws.com
docker tag vizier-med-backend:latest <account-id>.dkr.ecr.us-east-1.amazonaws.com/vizier-med-backend:latest
docker push <account-id>.dkr.ecr.us-east-1.amazonaws.com/vizier-med-backend:latest
```

### AWS Lambda (Serverless)

```bash
# Instalar Serverless Framework
npm install -g serverless

# Deploy
serverless deploy --stage prod
```

## Documentação API

A documentação interativa está disponível em:
- Swagger UI: http://localhost:8000/api/schema/swagger/
- ReDoc: http://localhost:8000/api/schema/redoc/

## Conformidade LGPD

- ✅ Audit logging de todas as operações
- ✅ Isolamento de dados por tenant
- ✅ Criptografia de dados em trânsito (HTTPS)
- ✅ Criptografia de dados em repouso (S3 SSE)
- ✅ Retenção de backups (7 dias)
- ✅ Permissões granulares por usuário

## Troubleshooting

### Erro de conexão com banco de dados

```bash
# Verificar se PostgreSQL está rodando
docker-compose ps

# Verificar logs
docker-compose logs db
```

### Erro de autenticação Cognito

- Verificar `COGNITO_USER_POOL_ID` e `COGNITO_CLIENT_ID`
- Confirmar que o token JWT é válido
- Verificar permissões do usuário no Cognito

### Erro ao processar DICOM

- Verificar formato do arquivo ZIP
- Confirmar que contém pasta `DICOM/` com estrutura correta
- Verificar logs: `docker-compose logs web`

## Contribuindo

1. Criar branch: `git checkout -b feature/sua-feature`
2. Commit: `git commit -am 'Adicionar feature'`
3. Push: `git push origin feature/sua-feature`
4. Abrir Pull Request

## Licença

Proprietary - Vizier Med

## Suporte

Para suporte, abrir issue no repositório ou contatar: support@viziermed.com

# Guia Docker - Vizier Med Backend

Documentação completa para executar a aplicação Vizier Med com Docker.

## Arquivos Docker Disponíveis

### Dockerfile (Desenvolvimento)
Otimizado para desenvolvimento local com hot-reload e debug mode.
- Python 3.11-slim
- Django development server
- Volume mount para código
- Debug mode ativo

### Dockerfile.prod (Produção)
Otimizado para produção com multi-stage build.
- Multi-stage build (builder + runtime)
- Gunicorn com 4 workers
- Usuário não-root
- Health checks integrados
- Tamanho de imagem reduzido (~400MB)

### docker-compose.yml (Desenvolvimento)
Orquestra serviços para desenvolvimento local.
- Django web (port 8000)
- PostgreSQL (port 5432)
- Redis (port 6379)
- Volume mounts para desenvolvimento

### docker-compose.prod.yml (Produção)
Orquestra serviços para produção.
- Django web (Gunicorn)
- PostgreSQL com persistência
- Redis com persistência
- Nginx reverse proxy (port 80/443)
- Health checks
- Restart policies

### nginx.conf
Configuração Nginx para produção.
- Proxy reverso para Django
- SSL/TLS
- Rate limiting
- Gzip compression
- Security headers
- Static files serving

## Execução Local (Desenvolvimento)

### 1. Build da imagem

```bash
docker-compose build
```

### 2. Iniciar serviços

```bash
docker-compose up -d
```

### 3. Verificar logs

```bash
docker-compose logs -f web
```

### 4. Acessar aplicação

- API: http://localhost:8000
- Admin: http://localhost:8000/admin/
- Health: http://localhost:8000/api/health/

### 5. Executar comandos Django

```bash
# Migrations
docker-compose exec web python manage.py migrate

# Criar superusuário
docker-compose exec web python manage.py createsuperuser

# Shell Django
docker-compose exec web python manage.py shell

# Testes
docker-compose exec web python manage.py test
```

### 6. Parar serviços

```bash
docker-compose down

# Com limpeza de volumes
docker-compose down -v
```

## Execução em Produção

### 1. Preparar arquivo .env

```bash
cp .env.example .env.prod

# Editar .env.prod com valores reais
cat > .env.prod << EOF
DEBUG=False
SECRET_KEY=your-very-secret-key-here
ALLOWED_HOSTS=yourdomain.com,www.yourdomain.com

DATABASE_URL=postgresql://vizier_user:strong_password@db:5432/vizier_med
REDIS_PASSWORD=strong_redis_password

COGNITO_REGION=us-east-1
COGNITO_USER_POOL_ID=us-east-1_xxxxxxxxx
COGNITO_CLIENT_ID=your-client-id

AWS_REGION=us-east-1
AWS_ACCESS_KEY_ID=your-access-key
AWS_SECRET_ACCESS_KEY=your-secret-key
S3_BUCKET=vizier-med-bucket

INFERENCE_API_URL=https://inference-api.example.com
INFERENCE_API_TIMEOUT=300

CREATE_SUPERUSER=true
SUPERUSER_PASSWORD=strong_password
EOF
```

### 2. Gerar certificados SSL (auto-signed para teste)

```bash
mkdir -p ssl
openssl req -x509 -newkey rsa:4096 -keyout ssl/key.pem -out ssl/cert.pem -days 365 -nodes
```

### 3. Build da imagem de produção

```bash
docker build -f Dockerfile.prod -t vizier-med-backend:latest .
```

### 4. Iniciar com docker-compose.prod.yml

```bash
docker-compose -f docker-compose.prod.yml --env-file .env.prod up -d
```

### 5. Verificar status

```bash
docker-compose -f docker-compose.prod.yml ps

# Logs
docker-compose -f docker-compose.prod.yml logs -f web

# Health check
curl https://localhost/api/health/
```

## Push para Registry (ECR, Docker Hub, etc)

### AWS ECR

```bash
# Login
aws ecr get-login-password --region us-east-1 | \
  docker login --username AWS --password-stdin 123456789.dkr.ecr.us-east-1.amazonaws.com

# Tag
docker tag vizier-med-backend:latest \
  123456789.dkr.ecr.us-east-1.amazonaws.com/vizier-med-backend:latest

# Push
docker push 123456789.dkr.ecr.us-east-1.amazonaws.com/vizier-med-backend:latest
```

### Docker Hub

```bash
# Login
docker login

# Tag
docker tag vizier-med-backend:latest yourusername/vizier-med-backend:latest

# Push
docker push yourusername/vizier-med-backend:latest
```

## Deploy em Produção (AWS ECS)

### 1. Criar task definition

```json
{
  "family": "vizier-med-backend",
  "networkMode": "awsvpc",
  "requiresCompatibilities": ["FARGATE"],
  "cpu": "512",
  "memory": "1024",
  "containerDefinitions": [
    {
      "name": "web",
      "image": "123456789.dkr.ecr.us-east-1.amazonaws.com/vizier-med-backend:latest",
      "portMappings": [
        {
          "containerPort": 8000,
          "hostPort": 8000,
          "protocol": "tcp"
        }
      ],
      "environment": [
        {
          "name": "DEBUG",
          "value": "False"
        }
      ],
      "secrets": [
        {
          "name": "SECRET_KEY",
          "valueFrom": "arn:aws:secretsmanager:us-east-1:123456789:secret:vizier/secret-key"
        }
      ],
      "logConfiguration": {
        "logDriver": "awslogs",
        "options": {
          "awslogs-group": "/ecs/vizier-med-backend",
          "awslogs-region": "us-east-1",
          "awslogs-stream-prefix": "ecs"
        }
      },
      "healthCheck": {
        "command": ["CMD-SHELL", "curl -f http://localhost:8000/api/health/ || exit 1"],
        "interval": 30,
        "timeout": 10,
        "retries": 3,
        "startPeriod": 40
      }
    }
  ]
}
```

### 2. Criar serviço ECS

```bash
aws ecs create-service \
  --cluster vizier-med \
  --service-name vizier-med-backend \
  --task-definition vizier-med-backend \
  --desired-count 2 \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[subnet-xxxxx,subnet-xxxxx],securityGroups=[sg-xxxxx],assignPublicIp=ENABLED}" \
  --load-balancers targetGroupArn=arn:aws:elasticloadbalancing:us-east-1:123456789:targetgroup/vizier-med/xxxxx,containerName=web,containerPort=8000
```

## Troubleshooting

### Erro: "Cannot connect to database"

```bash
# Verificar se PostgreSQL está rodando
docker-compose ps

# Verificar logs do banco
docker-compose logs db

# Reiniciar banco
docker-compose restart db
```

### Erro: "Port already in use"

```bash
# Mudar porta no docker-compose.yml
# Ou liberar porta
lsof -i :8000
kill -9 <PID>
```

### Erro: "Static files not found"

```bash
# Coletar static files
docker-compose exec web python manage.py collectstatic --noinput

# Verificar permissões
docker-compose exec web ls -la staticfiles/
```

### Erro: "Permission denied" (usuário não-root)

```bash
# Verificar permissões do volume
docker-compose exec web ls -la /app

# Corrigir permissões
docker-compose exec -u root web chown -R appuser:appuser /app
```

### Erro: "Out of memory"

```bash
# Aumentar memória no docker-compose.yml
# Ou limitar workers do Gunicorn
# Editar Dockerfile.prod: --workers 2 (ao invés de 4)
```

## Performance e Otimização

### Reduzir tamanho da imagem

```bash
# Multi-stage build (já implementado em Dockerfile.prod)
# Resultado: ~400MB ao invés de ~1GB

# Usar alpine ao invés de slim
# Já implementado
```

### Melhorar performance

```bash
# Aumentar workers Gunicorn
# Editar Dockerfile.prod: --workers 8

# Usar cache de Docker
docker build --cache-from vizier-med-backend:latest -f Dockerfile.prod .

# Usar BuildKit (mais rápido)
DOCKER_BUILDKIT=1 docker build -f Dockerfile.prod .
```

### Health checks

```bash
# Verificar health
curl http://localhost:8000/api/health/

# Resposta esperada:
# {"status": "healthy", "database": "connected", "redis": "connected"}
```

## Segurança

### Boas práticas

1. **Nunca commitar .env** - Usar .env.example
2. **Usar secrets manager** - AWS Secrets Manager, HashiCorp Vault
3. **Usuário não-root** - Já implementado (appuser)
4. **Read-only filesystem** - Considerar para produção
5. **Network isolation** - Usar security groups
6. **Scanning de vulnerabilidades** - `docker scan vizier-med-backend`

### Exemplo com Secrets Manager

```bash
# Armazenar secret
aws secretsmanager create-secret \
  --name vizier-med/secret-key \
  --secret-string "your-secret-key"

# Usar em task definition (veja exemplo acima)
```

## Monitoramento

### Logs

```bash
# Ver logs em tempo real
docker-compose logs -f web

# Ver logs de serviço específico
docker-compose logs db

# Ver últimas 100 linhas
docker-compose logs --tail=100 web
```

### Métricas

```bash
# CPU e memória
docker stats

# Detalhes do container
docker inspect vizier_web_1

# Eventos
docker events --filter container=vizier_web_1
```

### CloudWatch (AWS)

```bash
# Ver logs no CloudWatch
aws logs tail /ecs/vizier-med-backend --follow

# Criar alarme
aws cloudwatch put-metric-alarm \
  --alarm-name vizier-med-cpu \
  --alarm-description "Alert when CPU exceeds 80%" \
  --metric-name CPUUtilization \
  --namespace AWS/ECS \
  --statistic Average \
  --period 300 \
  --threshold 80 \
  --comparison-operator GreaterThanThreshold
```

## CI/CD com Docker

### GitHub Actions

```yaml
name: Build and Push Docker Image

on:
  push:
    branches: [main]

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v2
      
      - name: Login to ECR
        uses: aws-actions/amazon-ecr-login@v1
      
      - name: Build and push
        uses: docker/build-push-action@v4
        with:
          context: .
          file: ./Dockerfile.prod
          push: true
          tags: |
            ${{ secrets.ECR_REGISTRY }}/vizier-med-backend:latest
            ${{ secrets.ECR_REGISTRY }}/vizier-med-backend:${{ github.sha }}
```

## Referências

- [Docker Documentation](https://docs.docker.com/)
- [Docker Compose Documentation](https://docs.docker.com/compose/)
- [Django in Docker](https://docs.djangoproject.com/en/5.0/howto/deployment/wsgi/gunicorn/)
- [AWS ECS](https://docs.aws.amazon.com/ecs/)
- [Nginx Documentation](https://nginx.org/en/docs/)

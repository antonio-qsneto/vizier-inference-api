# Arquitetura - Vizier Med Backend

## Visão Geral

Vizier Med é uma aplicação SaaS backend construída com Django 5.0, seguindo as melhores práticas de arquitetura para 2025/2026 com foco em escalabilidade, segurança e conformidade LGPD.

## Decisões Arquiteturais

### 1. Framework: Django 5.0 + Django REST Framework

**Justificativa:**
- Maduro e bem documentado
- ORM poderoso para operações com banco de dados
- Segurança integrada (CSRF, SQL injection, XSS)
- Comunidade grande e ativa
- DRF para APIs RESTful modernas

### 2. Autenticação: AWS Cognito com JWT

**Justificativa:**
- Sem gerenciar senhas no Django
- Escalabilidade automática
- MFA integrado
- Conformidade com padrões de segurança
- Integração nativa com AWS

**Fluxo:**
```
Cliente → Cognito (login) → JWT Token
         ↓
Cliente → Django API (com JWT) → Validação JWT → Acesso autorizado
```

### 3. Multi-tenancy: Isolamento por Clinic

**Justificativa:**
- Cada clínica tem seus próprios dados
- Isolamento de segurança
- Billing por tenant
- Escalabilidade horizontal

**Implementação:**
- Campo `clinic` em modelos principais (Study, User)
- Middleware para filtrar queryset por clinic do usuário
- Permissões customizadas (IsClinicAdmin, etc)

### 4. Pipeline DICOM: Processamento Assíncrono

**Justificativa:**
- Operações de I/O pesadas (ZIP, DICOM, NPZ)
- Não bloqueia requisição HTTP
- Permite retry e tratamento de erro

**Fluxo:**
```
1. Upload DICOM ZIP
2. Validação e extração
3. Conversão DICOM → NPZ (com pré-processamento)
4. Submissão para API de inferência
5. Polling de status
6. Download de resultados
7. Conversão NPZ → NIfTI
8. Upload para S3
9. Retorno de URL assinada
```

### 5. Armazenamento: AWS S3 com URLs Assinadas

**Justificativa:**
- Escalabilidade ilimitada
- Custo baixo
- Integração nativa com AWS
- URLs assinadas para segurança

**Estrutura:**
```
s3://vizier-med-bucket/
├── results/
│   ├── {clinic_id}/
│   │   ├── {study_id}/
│   │   │   ├── image.nii.gz
│   │   │   └── mask.nii.gz
```

### 6. Banco de Dados: PostgreSQL com RDS

**Justificativa:**
- ACID compliance
- JSON support
- Full-text search
- Escalabilidade com RDS

**Schema:**
- Usuários (User)
- Clínicas (Clinic)
- Estudos (Study)
- Jobs (Job)
- Audit logs (AuditLog)

### 7. Cache: Redis

**Justificativa:**
- Cache de sessões
- Rate limiting
- Fila de jobs (futuro)
- Performance

### 8. Logging e Audit: AuditLog Model

**Justificativa:**
- Conformidade LGPD
- Rastreabilidade completa
- Detecção de anomalias

**Eventos registrados:**
- Login/logout
- Upload de estudos
- Acesso a resultados
- Convites de médicos
- Remoção de usuários

## Estrutura de Apps

### accounts
- Autenticação com Cognito
- Gerenciamento de usuários
- Permissões customizadas

### tenants
- Gerenciamento de clínicas
- Convites de médicos
- Planos de subscrição (placeholder)

### studies
- Criação de estudos
- Processamento DICOM
- Status e resultados

### inference
- Cliente para API externa
- Submissão de jobs
- Polling de status

### audit
- Logging de eventos
- Conformidade LGPD
- Relatórios

### health
- Health checks
- Monitoramento

## Fluxo de Requisição

```
1. Cliente envia JWT no header Authorization
2. Middleware CognitoJWTAuthentication valida JWT
3. User é recuperado/criado no Django
4. View processa requisição com permissões
5. Resposta é retornada com status apropriado
```

## Tratamento de Erros

**Exceções customizadas:**
- `ValidationError` - Dados inválidos
- `PermissionDenied` - Acesso negado
- `NotFound` - Recurso não encontrado
- `InferenceAPIError` - Erro na API de inferência

**Handler customizado:**
- Retorna JSON com erro e mensagem
- Log automático de erros
- Status HTTP apropriado

## Segurança

### Autenticação
- JWT via AWS Cognito
- Validação de assinatura
- Expiração de token

### Autorização
- Permissões por role (ADMIN, DOCTOR)
- Isolamento por clinic
- Validação de ownership

### Dados em Trânsito
- HTTPS obrigatório
- CORS configurado

### Dados em Repouso
- Criptografia S3 (SSE-S3)
- Criptografia RDS (KMS)
- Senhas com hash

## Escalabilidade

### Horizontal
- Stateless Django (sem sessões em memória)
- Redis para cache compartilhado
- RDS com read replicas

### Vertical
- Gunicorn com múltiplos workers
- Database pooling
- Cache agressivo

## Monitoramento

- CloudWatch para logs
- X-Ray para tracing
- Métricas de performance
- Alertas automáticos

## Deployment

### Desenvolvimento
- Docker Compose local
- SQLite ou PostgreSQL local
- Debug mode ativo

### Staging
- ECS no AWS
- RDS PostgreSQL
- S3 real
- Cognito real

### Produção
- ECS com auto-scaling
- RDS Multi-AZ
- CloudFront para CDN
- WAF para proteção
- Backup automático

## Roadmap

### Fase 1 (Atual)
- ✅ Autenticação Cognito
- ✅ Multi-tenancy
- ✅ Pipeline DICOM
- ✅ Integração S3
- ✅ Audit logging

### Fase 2
- Fila de jobs (Celery + Redis)
- Webhooks para eventos
- Relatórios avançados
- API de analytics

### Fase 3
- Integração com PACS
- Visualizador DICOM web
- Colaboração em tempo real
- Machine learning customizado

## Referências

- [Django Best Practices 2025](https://docs.djangoproject.com/)
- [AWS SaaS Best Practices](https://aws.amazon.com/saas/)
- [LGPD Compliance](https://www.gov.br/cidadania/pt-br/acesso-a-informacao/lgpd)
- [OWASP Top 10](https://owasp.org/www-project-top-ten/)

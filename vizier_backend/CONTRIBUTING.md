# Guia de Contribuição - Vizier Med

## Começando

### Configuração do Ambiente

1. Fork o repositório
2. Clone seu fork: `git clone https://github.com/seu-usuario/vizier-backend.git`
3. Adicione upstream: `git remote add upstream https://github.com/vizier-med/vizier-backend.git`
4. Crie ambiente virtual: `python3.11 -m venv venv && source venv/bin/activate`
5. Instale dependências: `pip install -r requirements.txt && pip install -r requirements-dev.txt`

### Executar Testes Localmente

```bash
# Todos os testes
python manage.py test

# Teste específico
python manage.py test apps.accounts.tests

# Com cobertura
coverage run --source='.' manage.py test
coverage report
```

### Linting e Formatação

```bash
# Verificar estilo
flake8 apps/ vizier_backend/ services/ --max-line-length=120

# Formatar código
black apps/ vizier_backend/ services/

# Organizar imports
isort apps/ vizier_backend/ services/
```

## Processo de Contribuição

### 1. Criar Branch

```bash
git checkout -b feature/descricao-da-feature
# ou
git checkout -b fix/descricao-do-bug
```

### 2. Fazer Alterações

- Escrever código limpo e bem documentado
- Adicionar testes para novas funcionalidades
- Atualizar documentação conforme necessário

### 3. Commit

```bash
# Commits atômicos com mensagens descritivas
git commit -m "feat: adicionar novo endpoint de estudos"
git commit -m "fix: corrigir erro de validação DICOM"
git commit -m "docs: atualizar README com instruções"
```

**Formato de mensagem:**
- `feat:` Nova funcionalidade
- `fix:` Correção de bug
- `docs:` Documentação
- `test:` Testes
- `refactor:` Refatoração
- `perf:` Melhoria de performance
- `chore:` Tarefas de manutenção

### 4. Push e Pull Request

```bash
git push origin feature/descricao-da-feature
```

Abra um Pull Request com:
- Descrição clara do que foi alterado
- Referência a issues relacionadas (#123)
- Screenshots se aplicável
- Checklist de testes

## Padrões de Código

### Python

```python
# Imports organizados
import os
import sys
from typing import Optional

from django.conf import settings
from rest_framework import serializers

from .models import User

# Docstrings
def process_dicom(file_path: str) -> dict:
    """
    Process DICOM file and return metadata.
    
    Args:
        file_path: Path to DICOM file
    
    Returns:
        Dictionary with metadata
    
    Raises:
        ValueError: If file is invalid
    """
    pass

# Type hints
def get_user(user_id: int) -> Optional[User]:
    """Get user by ID."""
    return User.objects.filter(id=user_id).first()
```

### Django Models

```python
class Study(models.Model):
    """Study model for DICOM processing."""
    
    # Fields
    clinic = models.ForeignKey(Clinic, on_delete=models.CASCADE)
    owner = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    category = models.CharField(max_length=255)
    status = models.CharField(
        max_length=20,
        choices=STUDY_STATUS_CHOICES,
        default='PENDING'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['clinic', 'owner']),
            models.Index(fields=['status']),
        ]
    
    def __str__(self) -> str:
        """Return study string representation."""
        return f"Study {self.id} - {self.category}"
    
    def is_completed(self) -> bool:
        """Check if study is completed."""
        return self.status == 'COMPLETED'
```

### Django Views

```python
class StudyViewSet(viewsets.ModelViewSet):
    """ViewSet for Study model."""
    
    queryset = Study.objects.all()
    serializer_class = StudySerializer
    permission_classes = [IsAuthenticated, IsClinicAdmin]
    
    def get_queryset(self):
        """Filter studies by clinic."""
        return self.queryset.filter(clinic=self.request.user.clinic)
    
    @action(detail=True, methods=['get'])
    def status(self, request, pk=None):
        """Get study status."""
        study = self.get_object()
        serializer = StudyStatusSerializer(study)
        return Response(serializer.data)
```

## Testes

### Estrutura de Testes

```python
from django.test import TestCase
from rest_framework.test import APITestCase

class StudyModelTest(TestCase):
    """Test Study model."""
    
    def setUp(self):
        """Set up test data."""
        self.clinic = Clinic.objects.create(name="Test Clinic")
        self.study = Study.objects.create(
            clinic=self.clinic,
            category="Brain"
        )
    
    def test_study_creation(self):
        """Test study creation."""
        self.assertEqual(self.study.category, "Brain")
        self.assertEqual(self.study.status, "PENDING")
    
    def test_study_is_completed(self):
        """Test is_completed method."""
        self.assertFalse(self.study.is_completed())
        self.study.status = 'COMPLETED'
        self.assertTrue(self.study.is_completed())
```

### Cobertura de Testes

- Mínimo 80% de cobertura
- Testes unitários para modelos e serviços
- Testes de integração para APIs
- Testes de ponta a ponta para fluxos críticos

## Documentação

### Docstrings

```python
def process_study(study_id: int) -> bool:
    """
    Process a study asynchronously.
    
    Converts DICOM ZIP to NPZ, submits to inference API,
    and stores results in S3.
    
    Args:
        study_id: ID of the study to process
    
    Returns:
        True if processing started successfully
    
    Raises:
        Study.DoesNotExist: If study not found
        ValueError: If study data is invalid
    
    Example:
        >>> process_study(123)
        True
    """
    pass
```

### README para Novos Recursos

Quando adicionar novo app ou serviço, criar README.md:

```markdown
# App Name

## Descrição
Breve descrição do que o app faz.

## Models
- Model1: Descrição
- Model2: Descrição

## APIs
- GET /api/endpoint/ - Descrição
- POST /api/endpoint/ - Descrição

## Configuração
Variáveis de ambiente necessárias.
```

## Checklist de Pull Request

- [ ] Código segue os padrões do projeto
- [ ] Testes adicionados/atualizados
- [ ] Cobertura de testes >= 80%
- [ ] Documentação atualizada
- [ ] Sem conflitos com main
- [ ] Commits com mensagens claras
- [ ] Sem prints ou código de debug
- [ ] Variáveis de ambiente documentadas

## Processo de Review

1. Pelo menos 2 aprovações necessárias
2. CI/CD deve passar (testes, linting)
3. Sem merge conflicts
4. Squash commits se necessário

## Releases

### Versionamento Semântico

- MAJOR: Mudanças incompatíveis
- MINOR: Novas funcionalidades compatíveis
- PATCH: Correções de bugs

### Processo de Release

1. Atualizar versão em `__init__.py`
2. Atualizar CHANGELOG.md
3. Criar tag: `git tag v1.2.3`
4. Push tag: `git push origin v1.2.3`
5. GitHub Actions faz deploy automático

## Reportar Bugs

Use o template de issue:

```markdown
## Descrição
Descrição clara do bug.

## Passos para Reproduzir
1. Passo 1
2. Passo 2
3. Passo 3

## Comportamento Esperado
O que deveria acontecer.

## Comportamento Atual
O que está acontecendo.

## Logs/Screenshots
Adicione logs ou screenshots relevantes.

## Ambiente
- Python: 3.11
- Django: 5.0
- OS: Ubuntu 22.04
```

## Sugestões de Funcionalidades

Use o template de feature request:

```markdown
## Descrição
Descrição clara da funcionalidade.

## Caso de Uso
Por que essa funcionalidade é necessária.

## Solução Proposta
Como você imagina que seria implementado.

## Alternativas Consideradas
Outras abordagens possíveis.
```

## Comunicação

- Issues: Para bugs e features
- Discussions: Para perguntas e ideias
- Email: support@viziermed.com para assuntos sensíveis

## Código de Conduta

- Seja respeitoso
- Aceite críticas construtivas
- Foque no código, não na pessoa
- Reporte comportamento inadequado

## Dúvidas?

Abra uma discussion ou envie email para support@viziermed.com

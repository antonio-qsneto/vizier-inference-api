# Fluxo de Cadastro e Convite de Clínica e Médicos

## Visão Geral

O aplicativo suporta **dois tipos de usuários**:

1. **Médicos Independentes (INDIVIDUAL)** - Sem vínculo a nenhuma clínica
2. **Médicos de Clínica (CLINIC_DOCTOR)** - Associados a uma clínica específica via convite

## Fluxo 1: Criar Clínica (CLINIC_ADMIN)

### Passo 1: Usuário faz login via Cognito

```bash
# O usuário se cadastra no Cognito e faz login
# Será criado como INDIVIDUAL por padrão
```

### Passo 2: Criar Clínica

```bash
TOKEN="seu_access_token"
curl -X POST "http://localhost:8000/api/clinics/clinics/" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Clínica Santa Maria",
    "cnpj": "12345678000190",
    "seat_limit": 10
  }'
```

**Resposta:**
```json
{
  "id": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
  "name": "Clínica Santa Maria",
  "cnpj": "12345678000190",
  "owner": {
    "id": 1,
    "email": "owner@example.com",
    "first_name": "João",
    "last_name": "Silva",
    "role": "CLINIC_ADMIN"
  },
  "seat_limit": 10,
  "subscription_plan": "free",
  "active_doctors_count": 0,
  "created_at": "2026-02-20T22:00:00Z",
  "updated_at": "2026-02-20T22:00:00Z"
}
```

**O quê acontece:**
- ✓ Usuário que fez a requisição agora é `CLINIC_ADMIN`
- ✓ Usuário é associado à clínica criada
- ✓ Clínica está pronta para receber médicos

---

## Fluxo 2: Convidar Médicos à Clínica

### Passo 3: CLINIC_ADMIN envia convite a médico

```bash
TOKEN="access_token_do_clinic_admin"
curl -X POST "http://localhost:8000/api/clinics/clinics/invite/" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "dr.carlos@clinicasantamaria.com.br"
  }'
```

**Resposta:**
```json
{
  "id": "yyyyyyyy-yyyy-yyyy-yyyy-yyyyyyyyyyyy",
  "clinic_name": "Clínica Santa Maria",
  "email": "dr.carlos@clinicasantamaria.com.br",
  "invited_by_email": "owner@example.com",
  "status": "PENDING",
  "created_at": "2026-02-20T22:05:00Z",
  "expires_at": "2026-02-27T22:05:00Z",
  "accepted_at": null
}
```

**O quê acontece:**
- ✓ Convite criado com status `PENDING`
- ✓ Válido por 7 dias
- ✓ Médico em `dr.carlos@clinicasantamaria.com.br` receberá email com instrução (quando implementado)

---

## Fluxo 3: Médico Aceita Convite (Opção A - Auto-accept via Login)

### Passo 4a: Médico se cadastra no Cognito COM o email do convite

```bash
# Médico faz signup no Cognito
# Email: dr.carlos@clinicasantamaria.com.br
# Senha: senha segura

# Após login, o JWT access_token é retornado
TOKEN="novo_access_token_do_dr_carlos"
```

### Passo 5a: Backend auto-aceita convite

Quando o médico faz a requisição autenticada, a middleware `CognitoJWTAuthentication`:

1. Valida o token
2. Cria/atualiza usuário no banco
3. **Verifica se há convites pendentes** para o email `dr.carlos@clinicasantamaria.com.br`
4. **Auto-aceita** o convite (se houver apenas um válido)
5. Muda role para `CLINIC_DOCTOR`
6. Vincula à clínica

**Resultado:**
```bash
# LOG no backend
✓ Auto-accepted invitation for dr.carlos@clinicasantamaria.com.br to clinic Clínica Santa Maria
```

---

## Fluxo 3B: Médico Aceita Convite (Opção B - Aceitar Manualmente)

### Passo 4b: Médico faz login e vê convites pendentes

```bash
TOKEN="access_token_do_dr_carlos"
curl -X GET "http://localhost:8000/api/doctor-invitations/my_invitations/" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json"
```

**Resposta:**
```json
[
  {
    "id": "yyyyyyyy-yyyy-yyyy-yyyy-yyyyyyyyyyyy",
    "clinic_name": "Clínica Santa Maria",
    "email": "dr.carlos@clinicasantamaria.com.br",
    "invited_by_email": "owner@example.com",
    "status": "PENDING",
    "created_at": "2026-02-20T22:05:00Z",
    "expires_at": "2026-02-27T22:05:00Z",
    "accepted_at": null
  }
]
```

### Passo 5b: Médico aceita o convite manualmente

```bash
TOKEN="access_token_do_dr_carlos"
INVITATION_ID="yyyyyyyy-yyyy-yyyy-yyyy-yyyyyyyyyyyy"

curl -X POST "http://localhost:8000/api/doctor-invitations/${INVITATION_ID}/accept/" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json"
```

**Resposta:**
```json
{
  "id": "yyyyyyyy-yyyy-yyyy-yyyy-yyyyyyyyyyyy",
  "clinic_name": "Clínica Santa Maria",
  "email": "dr.carlos@clinicasantamaria.com.br",
  "invited_by_email": "owner@example.com",
  "status": "ACCEPTED",
  "created_at": "2026-02-20T22:05:00Z",
  "expires_at": "2026-02-27T22:05:00Z",
  "accepted_at": "2026-02-20T22:10:00Z"
}
```

**O quê acontece:**
- ✓ Convite marcado como `ACCEPTED`
- ✓ Usuário role muda para `CLINIC_DOCTOR`
- ✓ Usuário vinculado à clínica
- ✓ Agora pode acessar recursos da clínica

---

## Fluxo 4: Verificar Médicos da Clínica

### Passo 6: CLINIC_ADMIN lista médicos da clínica

```bash
TOKEN="access_token_do_clinic_admin"
curl -X GET "http://localhost:8000/api/clinics/clinics/doctors/" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json"
```

**Resposta:**
```json
[
  {
    "id": "zzzzzzzz-zzzz-zzzz-zzzz-zzzzzzzzzzzz",
    "email": "dr.carlos@clinicasantamaria.com.br",
    "first_name": "Carlos",
    "last_name": "Oliveira",
    "role": "CLINIC_DOCTOR",
    "clinic_id": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
    "is_active": true,
    "created_at": "2026-02-20T22:10:00Z"
  }
]
```

---

## Fluxo 5: Médico Independente Permanece INDIVIDUAL

### Passo 7: Usuário sem convite continua INDIVIDUAL

```bash
# Usuário faz login sem convite
TOKEN="access_token_independente"

curl -X GET "http://localhost:8000/api/auth/users/me/" \
  -H "Authorization: Bearer $TOKEN"
```

**Resposta:**
```json
{
  "id": 5,
  "email": "dr.independente@example.com",
  "first_name": "Pedro",
  "last_name": "Independente",
  "cognito_sub": "us-east-1_xxxxx_uuid",
  "role": "INDIVIDUAL",
  "clinic_id": null,
  "is_active": true,
  "created_at": "2026-02-20T22:15:00Z"
}
```

- ✓ Sem vínculo com clínica
- ✓ Pode fazer upload de estudos diretamente
- ✓ Pode convidar apenas a si próprio

---

## Resumo de Estados

| Estado | Role | Clinic | Descrição |
|--------|------|--------|-----------|
| **Novo Login** | INDIVIDUAL | None | Usuário que acabou de fazer login |
| **Com Convite Aceito** | CLINIC_DOCTOR | ID | Médico convidado e aceitou |
| **Criador de Clínica** | CLINIC_ADMIN | ID | Dono/Admin da clínica |
| **Independente** | INDIVIDUAL | None | Sem vínculo com clínica |

---

## Endpoint Summary

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| **POST** | `/api/clinics/clinics/` | Criar clínica (usuário vira CLINIC_ADMIN) |
| **POST** | `/api/clinics/clinics/invite/` | CLINIC_ADMIN convida médico por email |
| **GET** | `/api/doctor-invitations/my_invitations/` | Ver convites pendentes do meu email |
| **POST** | `/api/doctor-invitations/{id}/accept/` | Aceitar convite específico |
| **GET** | `/api/clinics/clinics/doctors/` | CLINIC_ADMIN lista médicos da clínica |
| **DELETE** | `/api/clinics/clinics/remove_doctor/` | CLINIC_ADMIN remove médico |

---

## Observações Importantes

1. **Auto-accept** acontece no login automático via `CognitoJWTAuthentication`
2. Um usuário **NÃO pode** pertencer a duas clínicas
3. Convites expiram em **7 dias**
4. Convites **PENDING** só podem ser aceitos uma vez
5. **CLINIC_ADMIN** pode convidar, remover e ver médicos
6. **CLINIC_DOCTOR** acessa recursos apenas da sua clínica
7. **INDIVIDUAL** acessa seus próprios recursos

---

## Testes Recomendados

```bash
# 1. Criar usuário CLINIC_ADMIN
# 2. Convidar médico via email
# 3. Novo usuário faz login com email convidado
# 4. Verificar se foi auto-aceitado (role = CLINIC_DOCTOR)
# 5. Listar médicos da clínica
# 6. Médico independente fazer upload de estudo
# 7. CLINIC_DOCTOR fazer upload de estudo (vinculado à clínica)
```

# Configuração para Testar Fluxo de Clínica e Médicos

## 1️⃣ Variáveis de Ambiente Necessárias

Adicione ao `.env` (ou já devem estar lá):

```bash
# ============== COGNITO ==============
COGNITO_REGION=us-east-1
COGNITO_USER_POOL_ID=us-east-1_xxxxxxxxx
COGNITO_CLIENT_ID=xxxxxxxxxxxxxxxxxxxxxxxxxx
COGNITO_CLIENT_SECRET=seu-client-secret
COGNITO_DOMAIN=vizier-med-123456789

# ============== DJANGO ==============
DEBUG=True
SECRET_KEY=dev-secret-key-change-in-production
ALLOWED_HOSTS=localhost,127.0.0.1,web

# ============== DATABASE ==============
DATABASE_URL=postgresql://vizier_user:vizier_password@db:5432/vizier_med

# ============== SEAT LIMIT CHECK ==============
ENABLE_SEAT_LIMIT_CHECK=True  # Controla se verifica seat_limit na clínica
```

## 2️⃣ Criar Usuários de Teste no Cognito

Via AWS CLI:

```bash
# Usuário OWNER (criará a clínica)
aws cognito-idp admin-create-user \
  --user-pool-id us-east-1_xxxxxxxxx \
  --username owner@example.com \
  --user-attributes Name=email,Value=owner@example.com Name=email_verified,Value=true \
  --message-action SUPPRESS \
  --region us-east-1

aws cognito-idp admin-set-user-password \
  --user-pool-id us-east-1_xxxxxxxxx \
  --username owner@example.com \
  --password OwnerPassword123! \
  --permanent \
  --region us-east-1

# Usuário DOCTOR (receberá convite)
aws cognito-idp admin-create-user \
  --user-pool-id us-east-1_xxxxxxxxx \
  --username dr.carlos@example.com \
  --user-attributes Name=email,Value=dr.carlos@example.com Name=email_verified,Value=true \
  --message-action SUPPRESS \
  --region us-east-1

aws cognito-idp admin-set-user-password \
  --user-pool-id us-east-1_xxxxxxxxx \
  --username dr.carlos@example.com \
  --password DoctorPassword123! \
  --permanent \
  --region us-east-1

# Usuário INDEPENDENTE (não receberá convite)
aws cognito-idp admin-create-user \
  --user-pool-id us-east-1_xxxxxxxxx \
  --username independent@example.com \
  --user-attributes Name=email,Value=independent@example.com Name=email_verified,Value=true \
  --message-action SUPPRESS \
  --region us-east-1

aws cognito-idp admin-set-user-password \
  --user-pool-id us-east-1_xxxxxxxxx \
  --username independent@example.com \
  --password IndependentPassword123! \
  --permanent \
  --region us-east-1
```

## 3️⃣ Executar o Script de Teste

```bash
cd /home/antonio/medIA/development/vizier-inference-api/vizier_backend

# Dar permissão
chmod +x test_clinic_and_invitation_flow.sh

# Rodar teste
./test_clinic_and_invitation_flow.sh
```

## 4️⃣ Testes Manuais com Postman/cURL

### 4a. Owner faz Login

```bash
TOKEN_RESPONSE=$(aws cognito-idp admin-initiate-auth \
  --user-pool-id us-east-1_xxxxxxxxx \
  --client-id xxxxxxxxxxxxxxxxxxxxxxxxxx \
  --auth-flow ADMIN_NO_SRP_AUTH \
  --auth-parameters USERNAME=owner@example.com,PASSWORD=OwnerPassword123! \
  --region us-east-1)

OWNER_TOKEN=$(echo $TOKEN_RESPONSE | jq -r '.AuthenticationResult.AccessToken')
echo "Owner Token: $OWNER_TOKEN"
```

### 4b. Owner Cria Clínica

```bash
curl -X POST "http://localhost:8000/api/clinics/clinics/" \
  -H "Authorization: Bearer $OWNER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Clínica Santa Maria",
    "cnpj": "12345678000190",
    "seat_limit": 10
  }' | jq .
```

Copie o `id` da resposta (CLINIC_ID).

### 4c. Owner Verifica seu Perfil (deve ser CLINIC_ADMIN)

```bash
curl -X GET "http://localhost:8000/api/auth/users/me/" \
  -H "Authorization: Bearer $OWNER_TOKEN" | jq .
```

Esperado:
```json
{
  "id": 1,
  "email": "owner@example.com",
  "role": "CLINIC_ADMIN",
  "clinic_id": "xxxxx-xxxxx-xxxxx",
  ...
}
```

### 4d. Owner Convida Médico

```bash
curl -X POST "http://localhost:8000/api/clinics/clinics/invite/" \
  -H "Authorization: Bearer $OWNER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "dr.carlos@example.com"
  }' | jq .
```

Copie o `id` do convite (INVITATION_ID).

### 4e. Médico Faz Login

```bash
DOCTOR_RESPONSE=$(aws cognito-idp admin-initiate-auth \
  --user-pool-id us-east-1_xxxxxxxxx \
  --client-id xxxxxxxxxxxxxxxxxxxxxxxxxx \
  --auth-flow ADMIN_NO_SRP_AUTH \
  --auth-parameters USERNAME=dr.carlos@example.com,PASSWORD=DoctorPassword123! \
  --region us-east-1)

DOCTOR_TOKEN=$(echo $DOCTOR_RESPONSE | jq -r '.AuthenticationResult.AccessToken')
echo "Doctor Token: $DOCTOR_TOKEN"
```

### 4f. Médico Verifica seu Perfil (Deve Ser CLINIC_DOCTOR - AUTO-ACCEPT!)

```bash
curl -X GET "http://localhost:8000/api/auth/users/me/" \
  -H "Authorization: Bearer $DOCTOR_TOKEN" | jq .
```

Esperado:
```json
{
  "id": 2,
  "email": "dr.carlos@example.com",
  "role": "CLINIC_DOCTOR",
  "clinic_id": "xxxxx-xxxxx-xxxxx",
  ...
}
```

### 4g. Médico Ver Convites Pendentes (deve estar como ACCEPTED)

```bash
curl -X GET "http://localhost:8000/api/doctor-invitations/my_invitations/" \
  -H "Authorization: Bearer $DOCTOR_TOKEN" | jq .
```

Esperado:
```json
[
  {
    "id": "yyyyyyyy-yyyy-yyyy-yyyy-yyyyyyyyyyyy",
    "clinic_name": "Clínica Santa Maria",
    "email": "dr.carlos@example.com",
    "invited_by_email": "owner@example.com",
    "status": "ACCEPTED",
    "created_at": "...",
    "expires_at": "...",
    "accepted_at": "..."
  }
]
```

### 4h. Owner Lista Médicos da Clínica

```bash
curl -X GET "http://localhost:8000/api/clinics/clinics/doctors/" \
  -H "Authorization: Bearer $OWNER_TOKEN" | jq .
```

Esperado:
```json
[
  {
    "id": 2,
    "email": "dr.carlos@example.com",
    "first_name": "Carlos",
    "last_name": "Oliveira",
    "role": "CLINIC_DOCTOR",
    "clinic_id": "xxxxx-xxxxx-xxxxx",
    "is_active": true
  }
]
```

### 4i. Usuário Independente Faz Login (permanece INDIVIDUAL)

```bash
INDIE_RESPONSE=$(aws cognito-idp admin-initiate-auth \
  --user-pool-id us-east-1_xxxxxxxxx \
  --client-id xxxxxxxxxxxxxxxxxxxxxxxxxx \
  --auth-flow ADMIN_NO_SRP_AUTH \
  --auth-parameters USERNAME=independent@example.com,PASSWORD=IndependentPassword123! \
  --region us-east-1)

INDIE_TOKEN=$(echo $INDIE_RESPONSE | jq -r '.AuthenticationResult.AccessToken')

curl -X GET "http://localhost:8000/api/auth/users/me/" \
  -H "Authorization: Bearer $INDIE_TOKEN" | jq .
```

Esperado:
```json
{
  "id": 3,
  "email": "independent@example.com",
  "role": "INDIVIDUAL",
  "clinic_id": null,
  ...
}
```

## 5️⃣ Verificar Logs no Backend

```bash
# Ver logs do container web
docker-compose logs -f web

# Procurar por:
# ✓ Auto-accepted invitation for dr.carlos@example.com
# ✓ User already belongs to a clinic (se tentar criar outra clínica)
```

## 6️⃣ Testar Upload de Estudo

### 6a. Médico da Clínica Faz Upload (está vinculado)

```bash
# Com DOCTOR_TOKEN
curl -X POST "http://localhost:8000/api/studies/upload/" \
  -H "Authorization: Bearer $DOCTOR_TOKEN" \
  -F "file=@/path/to/study.zip" \
  -F "modality=CT"
# ✓ Deve funcionar (clinic_id será preenchido automaticamente)
```

### 6b. Médico Independente Faz Upload

```bash
# Com INDIE_TOKEN
curl -X POST "http://localhost:8000/api/studies/upload/" \
  -H "Authorization: Bearer $INDIE_TOKEN" \
  -F "file=@/path/to/study.zip" \
  -F "modality=CT"
# ✓ Deve funcionar também (serão seus próprios estudos)
```

---

## 📊 Checklist de Testes

- [ ] Owner cria clínica com sucesso
- [ ] Owner vira CLINIC_ADMIN
- [ ] Owner convida médico
- [ ] Médico faz login e é auto-aceitado
- [ ] Médico vira CLINIC_DOCTOR
- [ ] Convite aparece como ACCEPTED
- [ ] Owner vê médico na lista
- [ ] Independente continua INDIVIDUAL
- [ ] Independente não consegue criar clínica (já tem)
- [ ] CLINIC_DOCTOR não consegue criar outra clínica
- [ ] Upload de estudo funciona para ambos

---

## 🐛 Troubleshooting

### Erro: "User already belongs to a clinic"
→ Usuário já tem clínica vinculada. Normal se já foi convidado ou criou clínica antes.

### Erro: "Clinic has reached seat limit"
→ Muitos médicos já foram convidados. Aumentar `seat_limit` na clínica.

### Erro: "Invitation is for a different email"
→ Médico tentou aceitar convite de outro email. Fazer login com o email correto.

### Auto-accept não funcionou
→ Verificar logs: `docker-compose logs -f web | grep "Auto-accepted"`
→ Pode ser que convite expirou ou status não é PENDING

---

## 📝 Notas

1. **Auto-accept** acontece automaticamente na middleware quando o JWT é validado
2. Convites **expiram em 7 dias**
3. Um usuário **não pode** pertencer a 2 clínicas
4. **CLINIC_DOCTOR** não pode criar/convidar (apenas CLINIC_ADMIN)
5. **INDIVIDUAL** pode convidar a si próprio criando uma clínica (muda para CLINIC_ADMIN)

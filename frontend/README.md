# Vizier Med Frontend

Frontend React + TypeScript + Vite reconstruído para encaixar nos contratos reais do backend Django em `vizier_backend/`.

## O que está implementado

- Auth com Cognito Hosted UI + PKCE.
- Fallback de desenvolvimento quando Cognito não está configurado.
- Guard de rotas e sessão persistida.
- Dashboard, clinic management, invitations, studies list, upload e study detail.
- Viewer PACS-like para `image.nii.gz` + `mask.nii.gz` com:
  - axial, coronal e sagittal sincronizados
  - overlay de máscara
  - opacidade ajustável
  - seleção de paleta de labels
  - window/level presets para CT e presets de intensidade para MR
  - cine mode
  - zoom, pan e reset
  - orientation markers
- Proxy local para assets `file://` retornados pelo backend em desenvolvimento.
- Billing adapter com mock fallback quando o backend não expõe checkout.

## Endpoints usados

- `GET /api/health/`
- `GET /api/auth/users/me/`
- `GET /api/auth/categories/`
- `GET /api/clinics/clinics/`
- `POST /api/clinics/clinics/`
- `POST /api/clinics/clinics/invite/`
- `GET /api/clinics/clinics/doctors/`
- `DELETE /api/clinics/clinics/remove_doctor/?doctor_id=<id>`
- `GET /api/clinics/doctor-invitations/`
- `GET /api/clinics/doctor-invitations/my_invitations/`
- `POST /api/clinics/doctor-invitations/<invitation_id>/accept/`
- `GET /api/studies/`
- `GET /api/studies/<study_id>/`
- `POST /api/studies/upload/`
- `GET /api/studies/<study_id>/status/`
- `GET /api/studies/<study_id>/result/`

## Upload contract

O formulário envia exatamente o que o serializer do backend exige:

- um dos campos de arquivo:
  - `dicom_zip`
  - `npz_file`
  - `nifti_file`
- `case_identification`
- `patient_name`
- `age`
- `exam_source`
- `exam_modality`
- `category_id`

O frontend deriva o nome correto do campo de arquivo pela extensão enviada.

## Ambiente

Copie `.env.example` e ajuste:

- `VITE_API_BASE_URL`
- `VITE_LOCAL_FILE_ROOTS`
- `VITE_COGNITO_REGION`
- `VITE_COGNITO_USER_POOL_ID`
- `VITE_COGNITO_CLIENT_ID`
- `VITE_COGNITO_DOMAIN`
- `VITE_COGNITO_REDIRECT_URI`
- `VITE_COGNITO_LOGOUT_URI`
- `VITE_STRIPE_PUBLISHABLE_KEY`
- `VITE_ENABLE_BILLING`
- `VITE_BILLING_CHECKOUT_ENDPOINT`

## Comandos

```bash
./node_modules/.bin/vite dev
./node_modules/.bin/tsc --noEmit
./node_modules/.bin/vite build
./node_modules/.bin/esbuild server/index.ts --platform=node --packages=external --bundle --format=esm --outdir=dist
./node_modules/.bin/vitest run
```

## Desenvolvimento local com assets `file://`

Quando o backend está em modo dev e `S3Utils.generate_presigned_url()` retorna `file://...`, o frontend transforma a URL para `GET /__vizier/local-file?path=...`.

O proxy só atende arquivos dentro de:

- `/tmp/vizier-med`
- `/tmp/vizier-analysis`

Se quiser customizar os roots permitidos, use `VITE_LOCAL_FILE_ROOTS` com uma lista separada por vírgula.

Isso funciona tanto no Vite dev server quanto no `frontend/server/index.ts`.

## Backend Docker + Frontend local

Para o viewer funcionar com o backend rodando em Docker, o container precisa escrever os arquivos em um diretório compartilhado com o host.

O compose do backend deve montar:

- `/tmp/vizier-med:/tmp/vizier-med`
- `/tmp/vizier-analysis:/tmp/vizier-analysis`

O frontend já está preparado para ler esses caminhos pelo proxy local.

No compose deste repositório, o backend Docker também usa:

- `extra_hosts: host.docker.internal:host-gateway`
- `INFERENCE_API_URL=http://host.docker.internal:18001`

Para o seu fluxo atual, rode no host:

```bash
aws ssm start-session \
  --target <instance-id> \
  --document-name AWS-StartPortForwardingSessionToRemoteHost \
  --parameters "host=['10.0.10.254'],portNumber=['8000'],localPortNumber=['18000']"
```

Em outro terminal:

```bash
socat TCP-LISTEN:18001,fork TCP:127.0.0.1:18000
```

Assim o container do Django acessa a inferência pelo endpoint `host.docker.internal:18001`.

## Integration Notes

- O backend não expõe endpoints Stripe/checkout neste repositório. O frontend já deixa o ponto de integração em `client/src/billing/adapter.ts`.
- O prompt original citava `GET /api/auth/me/`, mas o backend real expõe `GET /api/auth/users/me/`. O frontend usa o endpoint real.
- O manual mencionava `.dcm`, mas o serializer atual aceita `.zip`, `.npz`, `.nii` e `.nii.gz`. O upload UI segue o contrato real do backend.

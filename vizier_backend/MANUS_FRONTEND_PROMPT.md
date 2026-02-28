# Manus Prompt: Build a Production Frontend for Vizier Med

You are a senior frontend engineer. Build a production-ready React web app for **Vizier Med** (medical imaging SaaS) that integrates with an existing Django backend.

## Objective

Create a complete frontend application that supports:

- AWS Cognito authentication (signup/login/logout, token handling, protected routes)
- Tenant/clinic workflows (clinic creation, doctor invitations, invitation acceptance)
- Study workflows (upload, status tracking, results visualization)
- Plan selection and Stripe checkout flow
- CT/MR results visualization using `image.nii.gz` + `mask.nii.gz` in PACS-like interaction patterns

## Technical Stack

Use:

- React + TypeScript + Vite
- React Router
- TanStack Query (API state, caching, polling)
- UI framework (tailwind css) with clean medical-grade UX
- AWS Cognito auth integration via Hosted UI (Authorization Code + PKCE)
- Stripe.js for checkout
- A NIfTI-capable viewer for overlay visualization (prefer Niivue; use vtk.js if needed for missing features)
- Vitest + Testing Library for key flows

## Backend API Context

Base URL example: `http://localhost:8000`

Authentication:

- Send `Authorization: Bearer <access_token>` on protected endpoints.

Key endpoints to integrate:

- `GET /api/health/`
- `GET /api/auth/me/`
- `GET /api/auth/categories/`
- `GET /api/auth/users/me/`
- `GET /api/clinics/clinics/`
- `POST /api/clinics/clinics/`
- `POST /api/clinics/clinics/invite/`
- `GET /api/clinics/clinics/doctors/`
- `DELETE /api/clinics/clinics/remove_doctor/?doctor_id=<id>`
- `GET /api/clinics/doctor-invitations/my_invitations/`
- `POST /api/clinics/doctor-invitations/<invitation_id>/accept/`
- `GET /api/studies/`
- `POST /api/studies/upload/`
- `GET /api/studies/<study_id>/status/`
- `GET /api/studies/<study_id>/result/`
- `GET /api/studies/<study_id>/visualization/`

## Upload Contract

Use `multipart/form-data` on `POST /api/studies/upload/`.

Send:

- `file` (recommended generic field): accepts `.zip`, `.npz`, `.nii`, `.nii.gz`
- `category_id`: selected target id from categories catalog

Important:

- Do not send free-text prompt from frontend.
- Frontend sends `category_id`; backend resolves it to model `text_prompts`.

## Categories Catalog Contract

`GET /api/auth/categories/` returns a modality-based catalog.

UI behavior:

- First dropdown: modality (CT, MRI, Ultrasound, PET, Electron Microscopy, Lightsheet Microscopy)
- Second dropdown: target list filtered by selected modality
- Selected target `id` is sent as `category_id`

## Result Visualization Requirements (CT/MR PACS-like)

Build a study result viewer that:

- Loads `image_url` and `mask_url` from `/result/` (or `/visualization/`)
- Renders synchronized axial, coronal, sagittal views
- Supports overlay of segmentation mask over image
- Supports adjustable mask opacity
- Supports label color map selection
- Supports slice scrolling and cine mode
- Supports zoom, pan, reset view
- Shows orientation markers (R/L/A/P)
- Supports CT window/level presets:
  - Brain
  - Bone
  - Lung
  - Mediastinum
- Supports MR intensity presets:
  - Auto
  - Soft tissue
  - High contrast
- Includes loading/error states and retry actions

## Stripe Plan Selection

Build a pricing page with plans:

- Free
- Starter
- Professional
- Enterprise

Stripe requirements:

- Use Stripe.js client integration
- Add “Select plan” and “Upgrade” flows
- Implement a billing service adapter with configurable endpoint(s)
- If backend billing endpoints are missing, include a mock adapter and clear TODO integration points
- Support success/cancel return routes

## Pages and Main Flows

Implement at least:

- Auth: Login, Signup, Logout callback handling
- Dashboard: user summary, clinic status, recent studies
- Clinic management: create clinic, invite doctor, list doctors, remove doctor
- Invitations: list my invitations, accept invitation
- Studies list: table with status, owner, date, category
- New study upload: modality -> target -> file upload
- Study detail: status polling, timeline, open result viewer
- Result viewer: NIfTI image + mask overlay
- Billing/pricing: plan selection, Stripe checkout start

## State and UX Requirements

- Persist auth session securely
- Redirect unauthenticated users to login
- Poll `/status/` until terminal state (`COMPLETED` or `FAILED`)
- Once `COMPLETED`, enable “Open Viewer” action
- Show meaningful API errors
- Responsive layout for desktop and tablet

## Security and Compliance Notes

- Do not store PHI in localStorage beyond required auth/session data.
- Avoid verbose logs with sensitive payloads.
- Ensure token is removed on logout and expired-session fallback is handled.

## Environment Variables

Use `.env` keys similar to:

- `VITE_API_BASE_URL`
- `VITE_COGNITO_REGION`
- `VITE_COGNITO_USER_POOL_ID`
- `VITE_COGNITO_CLIENT_ID`
- `VITE_COGNITO_DOMAIN`
- `VITE_COGNITO_REDIRECT_URI`
- `VITE_COGNITO_LOGOUT_URI`
- `VITE_STRIPE_PUBLISHABLE_KEY`
- `VITE_ENABLE_BILLING`
- `VITE_BILLING_CHECKOUT_ENDPOINT`

## API Examples the App Must Implement

Upload example:

```bash
curl -X POST "http://localhost:8000/api/studies/upload/" \
  -H "Authorization: Bearer <token>" \
  -F "file=@/path/case_ct_01.nii.gz" \
  -F "category_id=ct_liver_tumors"
```

Status polling example:

```bash
curl -X GET "http://localhost:8000/api/studies/<study_id>/status/" \
  -H "Authorization: Bearer <token>"
```

Result example:

```bash
curl -X GET "http://localhost:8000/api/studies/<study_id>/result/" \
  -H "Authorization: Bearer <token>"
```

Expected result payload contains signed URLs:

```json
{
  "study_id": "uuid",
  "image_url": "https://...",
  "mask_url": "https://...",
  "expires_in": 3600,
  "image_file_name": "study_<id>_image.nii.gz",
  "mask_file_name": "study_<id>_mask.nii.gz"
}
```

## Deliverables

- Full React codebase with TypeScript
- Clear folder structure and reusable API client layer
- README with setup instructions, env vars, and run commands
- A short “Integration Notes” section listing any missing backend endpoint assumptions
- Basic tests for:
  - auth guard behavior
  - upload form submission
  - study status polling behavior
  - viewer rendering with mocked image/mask URLs

## Quality Bar

- The app must be implementation-ready and runnable, not a mockup.
- Use clean, maintainable architecture and typed API contracts.
- Prefer explicit error handling and deterministic behavior in async flows.

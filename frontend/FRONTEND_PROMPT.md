# frontend Prompt: Build a Production Frontend for Vizier Med

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
- profissional
- clinical

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
- Studies list: table with status, owner, date, category,
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




Use the categories catalog endpoint as the frontend source of truth.

**Source of truth**
- Endpoint: `GET /api/auth/categories/`
- Auth required: yes
- Backend returns the raw JSON from [`categories.json`](/home/antonio/medIA/development/vizier-inference-api/vizier_backend/data/categories.json), via [`apps/accounts/views.py#L59`](/home/antonio/medIA/development/vizier-inference-api/vizier_backend/apps/accounts/views.py#L59).

**How the frontend should work**
1. Load `GET /api/auth/categories/` after the user is authenticated.
2. Build the first dropdown from the top-level keys:
   - `CT`
   - `MRI`
   - `Ultrasound`
   - `PET`
   - `Lightsheet Microscopy`
3. When the user selects a modality, build the second dropdown from that modality’s inner keys.
4. The second dropdown value must be sent as `category_id`.
5. The first dropdown value must be sent as `exam_modality`.
6. The frontend should also show a preview of the targets inside the selected category/group, because the backend will generate prompts for all of them.

Important: the second dropdown is not a single lesion/organ target. It is a group/region bucket. The backend expands that group into multiple `text_prompts`.

**Current catalog**
```json
{
  "CT": {
    "head": ["head-neck cancer"],
    "torax": ["lung lesions", "COVID-19"],
    "abdomen": [
      "adrenocortical carcinoma",
      "kidney lesions/cysts L/R",
      "liver tumors",
      "pancreas tumors",
      "colon cancer primaries"
    ],
    "whole-body": ["whole-body lesion", "lymph nodes"]
  },
  "MRI": {
    "head": [
      "brain tumor",
      "stroke lesion",
      "GTVp/GTVn tumor",
      "vestibular schwannoma intra/extra-meatal",
      "non-enhancing tumor core",
      "non-enhancing FLAIR hyperintensity",
      "enhancing tissue",
      "resection cavity",
      "WM hyperintensities FLAIR/T1"
    ],
    "GU": ["prostate lesion"]
  },
  "Ultrasound": {
    "head": ["brain tumor"]
  },
  "PET": {
    "whole-body": ["whole-body lesion"]
  },
  "Lightsheet Microscopy": {
    "head": ["Alzheimer's plaque"]
  }
}
```

**Dropdown logic**
- If `exam_modality = CT`, category options are:
  - `head`
  - `torax`
  - `abdomen`
  - `whole-body`
- If `exam_modality = MRI`, category options are:
  - `head`
  - `GU`
- If `exam_modality = Ultrasound`, category options are:
  - `head`
- If `exam_modality = PET`, category options are:
  - `whole-body`
- If `exam_modality = Lightsheet Microscopy`, category options are:
  - `head`

**What the backend expects**
The upload serializer requires these fields in multipart form-data, defined in [`apps/studies/serializers.py#L70`](/home/antonio/medIA/development/vizier-inference-api/vizier_backend/apps/studies/serializers.py#L70):
- one file field: `dicom_zip` or `npz_file` or `nifti_file`
- `case_identification`
- `patient_name`
- `age`
- `exam_source`
- `exam_modality`
- `category_id`

For the category selection:
- `exam_modality` = selected modality
- `category_id` = selected group key

Example:
- modality selected: `MRI`
- second dropdown selected: `head`

Send:
```text
exam_modality = MRI
category_id = head
```

Not this:
```text
category_id = brain tumor
```

The backend still accepts target names for backward compatibility, but the new frontend should not rely on that. It should send the group key. This resolution happens in [`apps/studies/views.py#L756`](/home/antonio/medIA/development/vizier-inference-api/vizier_backend/apps/studies/views.py#L756).

**What happens after selection**
If the user selects:
- `exam_modality = MRI`
- `category_id = head`

The backend will generate `text_prompts` for every target inside `MRI > head`, such as:
```json
{
  "1": "Visualization of brain tumor in head MR",
  "2": "Visualization of stroke lesion in head MR",
  "3": "Visualization of GTVp/GTVn tumor in head MR",
  "4": "Visualization of vestibular schwannoma intra/extra-meatal in head MR",
  "5": "Visualization of non-enhancing tumor core in head MR",
  "6": "Visualization of non-enhancing FLAIR hyperintensity in head MR",
  "7": "Visualization of enhancing tissue in head MR",
  "8": "Visualization of resection cavity in head MR",
  "9": "Visualization of WM hyperintensities FLAIR/T1 in head MR",
  "instance_label": 0
}
```

If the user selects:
- `exam_modality = CT`
- `category_id = abdomen`

The backend will generate prompts for:
- adrenocortical carcinoma
- kidney lesions/cysts L/R
- liver tumors
- pancreas tumors
- colon cancer primaries

**Recommended frontend UX**
- Dropdown 1 label: `Exam Modality`
- Dropdown 2 label: `Target Group`
- Read-only preview below dropdown 2: `Included Segmentation Targets`
- Disable dropdown 2 until modality is selected
- Clear dropdown 2 whenever modality changes
- Show the included targets as chips or a list
- Submit exact backend values, not display-transformed strings

**Example frontend state**
```ts
type Catalog = Record<string, Record<string, string[]>>;

type UploadFormState = {
  caseIdentification: string;
  patientName: string;
  age: number | '';
  examSource: string;
  examModality: string;
  categoryId: string;
  file: File | null;
};
```

**Example UI behavior**
```ts
const modalities = Object.keys(catalog);

const categoryOptions = selectedModality
  ? Object.keys(catalog[selectedModality] || {})
  : [];

const includedTargets = selectedModality && selectedCategory
  ? catalog[selectedModality]?.[selectedCategory] || []
  : [];
```

**Example upload payload**
```ts
const formData = new FormData();
formData.append('nifti_file', file);
formData.append('case_identification', 'CASE-2026-001');
formData.append('patient_name', 'Maria Silva');
formData.append('age', '58');
formData.append('exam_source', 'Hospital Sao Pedro');
formData.append('exam_modality', 'MRI');
formData.append('category_id', 'head');
```

**Implementation note**
The frontend should not hardcode targets into the upload payload. It should only send:
- the selected modality
- the selected group/category


##### D. File Upload

* Drag & drop area
* Accepted formats:

  * `.dcm`
  * `.zip`
  * `.nii / .nii.gz`
* Display a list of uploaded files

## Project Overview:
- A professional clinical frontend for neurological cases and imaging exams
- Dark theme inspired by iCloud (sidebar: #252528, icons: #0195f8, header: #353539, background: #222223)
- Elegant design with gradient and frosted glass effects
- Complete sidebar navigation with mains sections

## Design Philosophy:
implement a modern clinical interface with:
- Frosted glass morphism for cards and panels (semi-transparent with backdrop blur)
- Gradient accents using the clinical blue (#0195f8) with subtle transitions
- Professional typography with clear hierarchy for medical readability
- Smooth micro-interactions for a polished, premium feel
- Accessibility-first design with proper contrast and spacing

# style
For the style, create an architecture that makes it easy for the developer to change the main colors and icons.

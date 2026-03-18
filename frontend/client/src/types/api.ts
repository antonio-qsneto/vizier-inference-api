export type UserRole = "CLINIC_ADMIN" | "CLINIC_DOCTOR" | "INDIVIDUAL" | string;
export type EffectiveRole =
  | "platform_admin"
  | "clinic_admin"
  | "clinic_doctor"
  | "individual"
  | string;
export type StudyStatusValue = "SUBMITTED" | "QUEUED" | "PROCESSING" | "COMPLETED" | "FAILED" | string;
export type InferenceJobStatusValue =
  | "CREATED"
  | "UPLOAD_PENDING"
  | "UPLOADED"
  | "VALIDATING"
  | "PREPROCESSING"
  | "QUEUED"
  | "RUNNING"
  | "POSTPROCESSING"
  | "COMPLETED"
  | "FAILED"
  | string;
export type ClinicPlanType = "individual" | "clinic" | string;
export type ClinicSubscriptionPlan = "free" | "clinic_monthly" | "clinic_yearly" | string;
export type ClinicAccountStatus = "active" | "past_due" | "canceled" | string;
export type AccountLifecycleStatus = "active" | "deleted" | string;

export interface HealthStatus {
  status: string;
  service: string;
  version: string;
}

export interface ConsultationRequestPayload {
  first_name?: string;
  last_name?: string;
  company_name?: string;
  job_title?: string;
  email: string;
  country: string;
  message?: string;
  discovery_source?: string;
}

export interface ConsultationRequestResponse {
  detail: string;
}

export interface UserProfile {
  id: number;
  email: string;
  full_name: string;
  first_name: string;
  last_name: string;
  role: UserRole;
  effective_role: EffectiveRole;
  clinic_id: string | null;
  clinic_name: string | null;
  subscription_plan: string | null;
  seat_limit: number | null;
  seat_used: number | null;
  account_status: ClinicAccountStatus | null;
  account_lifecycle_status: AccountLifecycleStatus;
  upload_enabled: boolean;
  notices: UserNotice[];
  is_active: boolean;
  created_at: string;
}

export interface UserNotice {
  id: string;
  type: string;
  title: string;
  message: string;
  payload: Record<string, unknown>;
  created_at: string;
}

export interface UserSummary {
  id: number;
  email: string;
  full_name: string;
  first_name: string;
  last_name: string;
  role: UserRole;
  clinic_id: string | null;
  clinic_name: string | null;
  is_active: boolean;
  created_at: string;
}

export interface Clinic {
  id: string;
  name: string;
  cnpj?: string | null;
  owner?: UserSummary | null;
  seat_limit?: number;
  seat_used?: number;
  subscription_plan?: ClinicSubscriptionPlan;
  plan_type?: ClinicPlanType;
  account_status?: ClinicAccountStatus;
  active_doctors_count?: number;
  scheduled_seat_limit?: number | null;
  scheduled_seat_effective_at?: string | null;
  has_pending_seat_reduction?: boolean;
  created_at?: string;
  updated_at?: string;
}

export interface DoctorInvitation {
  id: string;
  clinic_name: string;
  email: string;
  invited_by_email: string;
  status: string;
  created_at: string;
  expires_at: string;
  accepted_at: string | null;
}

export interface Job {
  id: string;
  external_job_id: string;
  status: StudyStatusValue;
  progress_percent: number;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
}

export interface StudyIngestionReport {
  source: string;
  layout?: string | null;
  selected_series_label?: string | null;
  selected_series_uid?: string | null;
  candidate_series_count?: number | null;
  effective_slices?: number | null;
  matrix?: number[] | null;
  slice_spacing?: number | null;
}

export interface Study {
  id: string;
  category: string;
  case_identification: string | null;
  patient_name: string | null;
  age: number | null;
  exam_source: string | null;
  exam_modality: string | null;
  status: StudyStatusValue;
  owner_email: string;
  job: Job | null;
  s3_key: string | null;
  image_s3_key: string | null;
  mask_s3_key: string | null;
  error_message: string | null;
  ingestion_report?: StudyIngestionReport | null;
  created_at: string;
  updated_at: string;
  completed_at: string | null;
}

export interface StudyStatus {
  id: string;
  status: StudyStatusValue;
  job_status: StudyStatusValue | null;
  job_progress: number | null;
  updated_at: string;
}

export interface SegmentLegendItem {
  id: number;
  label: string;
  prompt: string;
  voxels: number;
  fraction: number;
  percentage: number;
  color: string;
}

export interface StudyResult {
  study_id: string;
  image_url: string;
  mask_url: string;
  segments_legend: SegmentLegendItem[];
  descriptive_analysis?: string | null;
  expires_in: number;
  image_file_name: string;
  mask_file_name: string;
}

export interface InferenceUploadInstructions {
  method: "POST";
  url: string;
  fields: Record<string, string>;
  key: string;
  expires_in: number;
  bucket: string;
  input_artifact_id: string;
}

export interface InferenceJobCreateResponse {
  job_id: string;
  status: InferenceJobStatusValue;
  tenant_id: string;
  correlation_id: string;
  upload: InferenceUploadInstructions;
}

export interface InferenceInputArtifact {
  id: string;
  bucket: string;
  key: string;
  kind: string;
  original_filename: string | null;
  content_type: string | null;
  size_bytes: number | null;
  etag: string | null;
  upload_status: string;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface InferenceJobStatus {
  id: string;
  tenant: string;
  owner: number;
  request_payload?: Record<string, unknown> | null;
  status: InferenceJobStatusValue;
  progress_percent: number;
  requested_device: "cuda" | "cpu" | string;
  slice_batch_size: number | null;
  gpu_task_arn: string | null;
  attempt_count: number;
  correlation_id: string;
  idempotency_key: string | null;
  error_type: string | null;
  error_message: string | null;
  created_at: string;
  updated_at: string;
  uploaded_at: string | null;
  started_at: string | null;
  completed_at: string | null;
  input_artifacts: InferenceInputArtifact[];
}

export interface InferenceJobListItem {
  id: string;
  status: InferenceJobStatusValue;
  progress_percent: number;
  error_type: string | null;
  error_message: string | null;
  created_at: string;
  updated_at: string;
  completed_at: string | null;
  correlation_id: string;
  request_payload: Record<string, unknown> | null;
  owner_email: string;
}

export interface InferenceJobListResponse {
  count: number;
  results: InferenceJobListItem[];
}

export interface InferenceOutputArtifact {
  id: string;
  job: string;
  bucket: string;
  key: string;
  kind: string;
  content_type: string | null;
  size_bytes: number | null;
  etag: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
}

export interface InferenceJobOutputsResponse {
  job_id: string;
  status: InferenceJobStatusValue;
  outputs: InferenceOutputArtifact[];
}

export interface InferenceOutputPresignResponse {
  output_id: string;
  kind: string;
  url: string;
  expires_in: number;
}

export type CategoriesCatalog = Record<string, Record<string, string[]>>;

export interface PaginatedResponse<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

export interface ClinicCreatePayload {
  name: string;
  cnpj: string;
  seat_limit?: number;
  subscription_plan?: string;
}

export interface ClinicBillingPlan {
  id: "clinic_monthly" | "clinic_yearly";
  label: string;
  price_label: string;
  summary: string;
  interval: "month" | "year" | string;
  lookup_key: string;
  discount: string | null;
}

export interface ClinicBillingCatalogResponse {
  plans: ClinicBillingPlan[];
  current_plan: ClinicSubscriptionPlan;
  account_status: ClinicAccountStatus;
  seat_limit: number;
  seat_used: number;
  billing_enabled: boolean;
}

export interface ClinicBillingCheckoutResponse {
  mode?: "subscription_updated";
  detail?: string;
  checkout_url?: string;
  checkout_session_id?: string;
  seat_limit?: number;
  seat_used?: number;
}

export interface ClinicTeamMembersResponse {
  admins: UserSummary[];
  doctors: UserSummary[];
  seats_used: number;
  seat_limit: number;
  account_status: ClinicAccountStatus;
}

export interface ClinicSeatChangeResponse {
  detail: string;
  seat_limit: number;
  seat_used: number;
  scheduled_seat_limit: number | null;
  scheduled_seat_effective_at: string | null;
}

export interface ClinicBillingSyncResponse {
  detail: string;
  plan: ClinicSubscriptionPlan;
  account_status: ClinicAccountStatus;
  seat_limit: number;
  seat_used: number;
}

export interface IndividualBillingCancelResponse {
  detail: string;
  status: string;
  cancel_at_period_end: boolean;
  billing_period_end: string | null;
}

export interface IndividualBillingSyncResponse {
  detail: string;
  plan: string;
  status: string;
  billing_period_end: string | null;
}

export interface ClinicBillingCancelResponse {
  detail: string;
  account_status: ClinicAccountStatus;
  cancel_at_period_end: boolean;
  billing_period_end: string | null;
}

export interface ClinicDowngradeResponse {
  detail: string;
  plan_type: ClinicPlanType;
  account_status: ClinicAccountStatus;
  seat_limit: number;
  seat_used: number;
  scheduled_seat_limit?: number | null;
  scheduled_seat_effective_at?: string | null;
}

export interface ClinicLeaveResponse {
  detail: string;
  new_role: UserRole;
  clinic_id: string | null;
  subscription_plan: string;
}

export interface OffboardingBlocker {
  code: string;
  message: string;
}

export interface OffboardingStatus {
  effective_role: EffectiveRole;
  can_cancel_subscription: boolean;
  can_delete_account: boolean;
  blockers: OffboardingBlocker[];
  subscription_scope: "individual" | "clinic" | "none" | string;
  status: string | null;
  billing_period_end: string | null;
}

export interface StudyUploadInput {
  file: File;
  caseIdentification: string;
  patientName: string;
  age: number;
  examSource: string;
  examModality: string;
  categoryId: string;
}

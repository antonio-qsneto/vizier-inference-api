export type UserRole = "CLINIC_ADMIN" | "CLINIC_DOCTOR" | "INDIVIDUAL" | string;
export type StudyStatusValue = "SUBMITTED" | "QUEUED" | "PROCESSING" | "COMPLETED" | "FAILED" | string;

export interface HealthStatus {
  status: string;
  service: string;
  version: string;
}

export interface UserProfile {
  id: number;
  email: string;
  full_name: string;
  first_name: string;
  last_name: string;
  role: UserRole;
  clinic_id: string | null;
  clinic_name: string | null;
  subscription_plan: string | null;
  seat_limit: number | null;
  is_active: boolean;
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
  cnpj: string | null;
  owner: UserSummary;
  seat_limit: number;
  subscription_plan: string;
  active_doctors_count: number;
  created_at: string;
  updated_at: string;
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
  expires_in: number;
  image_file_name: string;
  mask_file_name: string;
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
  seat_limit: number;
  subscription_plan: string;
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

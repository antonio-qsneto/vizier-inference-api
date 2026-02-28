import { apiRequest, isPaginatedResponse } from "@/api/client";
import type {
  CategoriesCatalog,
  Clinic,
  ClinicCreatePayload,
  DoctorInvitation,
  HealthStatus,
  PaginatedResponse,
  Study,
  StudyResult,
  StudyStatus,
  StudyUploadInput,
  UserProfile,
  UserSummary,
} from "@/types/api";

export type UploadFieldName = "dicom_zip" | "npz_file" | "nifti_file";

export function pickUploadFieldName(fileName: string): UploadFieldName {
  const lowerFileName = fileName.toLowerCase();

  if (lowerFileName.endsWith(".zip")) {
    return "dicom_zip";
  }

  if (lowerFileName.endsWith(".npz")) {
    return "npz_file";
  }

  if (lowerFileName.endsWith(".nii") || lowerFileName.endsWith(".nii.gz")) {
    return "nifti_file";
  }

  throw new Error(
    "Unsupported file format. Use ZIP (.zip), NPZ (.npz), or NIfTI (.nii/.nii.gz).",
  );
}

export function buildStudyUploadFormData(input: StudyUploadInput) {
  const formData = new FormData();
  formData.append(pickUploadFieldName(input.file.name), input.file);
  formData.append("case_identification", input.caseIdentification);
  formData.append("patient_name", input.patientName);
  formData.append("age", String(input.age));
  formData.append("exam_source", input.examSource);
  formData.append("exam_modality", input.examModality);
  formData.append("category_id", input.categoryId);
  return formData;
}

export function getPageResults<T>(payload: PaginatedResponse<T> | T[]) {
  return isPaginatedResponse<T>(payload) ? payload.results : payload;
}

export async function fetchHealth(signal?: AbortSignal) {
  return apiRequest<HealthStatus>("/api/health/", { signal });
}

export async function fetchCurrentUser(token: string, signal?: AbortSignal) {
  return apiRequest<UserProfile>("/api/auth/users/me/", { token, signal });
}

export async function fetchCategories(token: string, signal?: AbortSignal) {
  return apiRequest<CategoriesCatalog>("/api/auth/categories/", { token, signal });
}

export async function fetchClinics(token: string, signal?: AbortSignal) {
  return apiRequest<PaginatedResponse<Clinic>>("/api/clinics/clinics/", {
    token,
    signal,
  });
}

export async function createClinic(
  token: string,
  payload: ClinicCreatePayload,
) {
  return apiRequest<Clinic>("/api/clinics/clinics/", {
    method: "POST",
    token,
    body: JSON.stringify(payload),
  });
}

export async function fetchClinicDoctors(token: string, signal?: AbortSignal) {
  return apiRequest<UserSummary[]>("/api/clinics/clinics/doctors/", {
    token,
    signal,
  });
}

export async function inviteDoctor(token: string, email: string) {
  return apiRequest<DoctorInvitation>("/api/clinics/clinics/invite/", {
    method: "POST",
    token,
    body: JSON.stringify({ email }),
  });
}

export async function removeDoctor(token: string, doctorId: number) {
  return apiRequest<{ status: string }>(
    `/api/clinics/clinics/remove_doctor/?doctor_id=${doctorId}`,
    {
      method: "DELETE",
      token,
    },
  );
}

export async function fetchClinicInvitations(
  token: string,
  signal?: AbortSignal,
) {
  return apiRequest<PaginatedResponse<DoctorInvitation>>(
    "/api/clinics/doctor-invitations/",
    {
      token,
      signal,
    },
  );
}

export async function fetchMyInvitations(token: string, signal?: AbortSignal) {
  return apiRequest<DoctorInvitation[]>(
    "/api/clinics/doctor-invitations/my_invitations/",
    {
      token,
      signal,
    },
  );
}

export async function acceptInvitation(token: string, invitationId: string) {
  return apiRequest<DoctorInvitation>(
    `/api/clinics/doctor-invitations/${invitationId}/accept/`,
    {
      method: "POST",
      token,
    },
  );
}

export async function fetchStudies(token: string, signal?: AbortSignal) {
  return apiRequest<PaginatedResponse<Study>>("/api/studies/", {
    token,
    signal,
  });
}

export async function fetchStudy(token: string, studyId: string, signal?: AbortSignal) {
  return apiRequest<Study>(`/api/studies/${studyId}/`, {
    token,
    signal,
  });
}

export async function uploadStudy(token: string, input: StudyUploadInput) {
  return apiRequest<Study>("/api/studies/upload/", {
    method: "POST",
    token,
    body: buildStudyUploadFormData(input),
  });
}

export async function fetchStudyStatus(
  token: string,
  studyId: string,
  signal?: AbortSignal,
) {
  return apiRequest<StudyStatus>(`/api/studies/${studyId}/status/`, {
    token,
    signal,
  });
}

export async function fetchStudyResult(
  token: string,
  studyId: string,
  signal?: AbortSignal,
) {
  return apiRequest<StudyResult>(`/api/studies/${studyId}/result/`, {
    token,
    signal,
  });
}

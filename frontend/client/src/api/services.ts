import { apiRequest, isPaginatedResponse } from "@/api/client";
import type { TokenExchangePayload } from "@/auth/session";
import type {
  CategoriesCatalog,
  ClinicBillingCancelResponse,
  ClinicBillingCatalogResponse,
  ClinicBillingCheckoutResponse,
  ClinicBillingSyncResponse,
  ClinicDowngradeResponse,
  ClinicLeaveResponse,
  ClinicSeatChangeResponse,
  Clinic,
  ClinicCreatePayload,
  ClinicTeamMembersResponse,
  DoctorInvitation,
  HealthStatus,
  IndividualBillingCancelResponse,
  IndividualBillingSyncResponse,
  OffboardingStatus,
  PaginatedResponse,
  Study,
  StudyResult,
  StudyStatus,
  StudyUploadInput,
  UserProfile,
  UserSummary,
} from "@/types/api";

export type UploadFieldName = "dicom_zip" | "npz_file" | "nifti_file";

export interface DevMockLoginPayload {
  email: string;
  password: string;
}

export interface DevMockSignupPayload extends DevMockLoginPayload {
  first_name?: string;
  last_name?: string;
}

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

export async function fetchOffboardingStatus(token: string, signal?: AbortSignal) {
  return apiRequest<OffboardingStatus>("/api/auth/users/offboarding_status/", {
    token,
    signal,
  });
}

export async function deleteAccount(
  token: string,
  payload: {
    confirm_text: string;
    current_password?: string;
  },
) {
  return apiRequest<{ detail: string }>("/api/auth/users/delete_account/", {
    method: "POST",
    token,
    body: JSON.stringify(payload),
  });
}

export async function devMockSignup(payload: DevMockSignupPayload) {
  return apiRequest<TokenExchangePayload>("/api/auth/dev/signup/", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function devMockLogin(payload: DevMockLoginPayload) {
  return apiRequest<TokenExchangePayload>("/api/auth/dev/login/", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function fetchCategories(token: string, signal?: AbortSignal) {
  return apiRequest<CategoriesCatalog>("/api/auth/categories/", {
    token,
    signal,
  });
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

export async function cancelIndividualBilling(token: string) {
  return apiRequest<IndividualBillingCancelResponse>("/api/auth/billing/cancel/", {
    method: "POST",
    token,
  });
}

export async function syncIndividualBilling(
  token: string,
  checkoutSessionId?: string,
) {
  return apiRequest<IndividualBillingSyncResponse>("/api/auth/billing/sync/", {
    method: "POST",
    token,
    body: JSON.stringify({
      checkout_session_id: checkoutSessionId,
    }),
  });
}

export async function fetchClinicTeamMembers(
  token: string,
  signal?: AbortSignal,
) {
  return apiRequest<ClinicTeamMembersResponse>("/api/clinics/clinics/team_members/", {
    token,
    signal,
  });
}

export async function fetchClinicBillingPlans(
  token: string,
  signal?: AbortSignal,
) {
  return apiRequest<ClinicBillingCatalogResponse>("/api/clinics/clinics/billing_plans/", {
    token,
    signal,
  });
}

export async function startClinicBillingCheckout(
  token: string,
  payload: {
    plan_id: "clinic_monthly" | "clinic_yearly";
    quantity?: number;
    success_url?: string;
    cancel_url?: string;
  },
) {
  return apiRequest<ClinicBillingCheckoutResponse>("/api/clinics/clinics/billing_checkout/", {
    method: "POST",
    token,
    body: JSON.stringify(payload),
  });
}

export async function startClinicBillingPortal(
  token: string,
  returnUrl?: string,
) {
  return apiRequest<{ url: string }>("/api/clinics/clinics/billing_portal/", {
    method: "POST",
    token,
    body: JSON.stringify({
      return_url: returnUrl,
    }),
  });
}

export async function syncClinicBilling(
  token: string,
  checkoutSessionId?: string,
) {
  return apiRequest<ClinicBillingSyncResponse>("/api/clinics/clinics/billing_sync/", {
    method: "POST",
    token,
    body: JSON.stringify({
      checkout_session_id: checkoutSessionId,
    }),
  });
}

export async function changeClinicSeats(
  token: string,
  targetQuantity: number,
) {
  return apiRequest<ClinicSeatChangeResponse>("/api/clinics/clinics/change_seats/", {
    method: "POST",
    token,
    body: JSON.stringify({ target_quantity: targetQuantity }),
  });
}

export async function downgradeClinicToIndividual(token: string) {
  return apiRequest<ClinicDowngradeResponse>("/api/clinics/clinics/downgrade_to_individual/", {
    method: "POST",
    token,
  });
}

export async function cancelClinicSubscription(token: string) {
  return apiRequest<ClinicBillingCancelResponse>("/api/clinics/clinics/cancel_subscription/", {
    method: "POST",
    token,
  });
}

export async function leaveClinic(token: string) {
  return apiRequest<ClinicLeaveResponse>("/api/clinics/clinics/leave_clinic/", {
    method: "POST",
    token,
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

export async function cancelInvitation(token: string, invitationId: string) {
  return apiRequest<DoctorInvitation>(
    `/api/clinics/doctor-invitations/${invitationId}/cancel/`,
    {
      method: "POST",
      token,
    },
  );
}

export async function acknowledgeNotices(
  token: string,
  noticeIds?: string[],
) {
  return apiRequest<{ acknowledged: number }>("/api/auth/users/acknowledge_notices/", {
    method: "POST",
    token,
    body: JSON.stringify(
      noticeIds && noticeIds.length ? { notice_ids: noticeIds } : {},
    ),
  });
}

export async function fetchStudies(token: string, signal?: AbortSignal) {
  return apiRequest<PaginatedResponse<Study>>("/api/studies/", {
    token,
    signal,
  });
}

export async function fetchStudy(
  token: string,
  studyId: string,
  signal?: AbortSignal,
) {
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

import { apiRequest, isPaginatedResponse } from "@/api/client";
import type { TokenExchangePayload } from "@/auth/session";
import type {
  ConsultationRequestPayload,
  ConsultationRequestResponse,
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
  InferenceJobCreateResponse,
  InferenceJobListResponse,
  InferenceJobOutputsResponse,
  InferenceJobStatus,
  InferenceOutputPresignResponse,
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
    "Formato de arquivo não suportado. Use ZIP (.zip), NPZ (.npz) ou NIfTI (.nii/.nii.gz).",
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

export interface InferenceJobCreateInput {
  fileName: string;
  fileSize: number;
  contentType: string;
  caseIdentification?: string;
  patientName?: string;
  age?: number;
  examSource?: string;
  examModality?: string;
  categoryId?: string;
  requestedDevice?: "cuda" | "cpu";
  sliceBatchSize?: number;
  correlationId?: string;
}

function extractArrayField<T>(payload: unknown): T[] | null {
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
    return null;
  }

  const record = payload as Record<string, unknown>;
  for (const key of ["results", "items", "data"]) {
    const candidate = record[key];
    if (Array.isArray(candidate)) {
      return candidate as T[];
    }
  }

  return null;
}

export function getPageResults<T>(payload: PaginatedResponse<T> | T[] | unknown): T[] {
  if (Array.isArray(payload)) {
    return payload;
  }

  if (isPaginatedResponse<T>(payload as { results?: T[] })) {
    return (payload as { results: T[] }).results;
  }

  const extracted = extractArrayField<T>(payload);
  if (extracted) {
    return extracted;
  }

  return [];
}

export async function fetchHealth(signal?: AbortSignal) {
  return apiRequest<HealthStatus>("/api/health/", { signal });
}

export async function submitConsultationRequest(
  payload: ConsultationRequestPayload,
) {
  return apiRequest<ConsultationRequestResponse>("/api/auth/consultation-request/", {
    method: "POST",
    body: JSON.stringify(payload),
  });
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
    clinic_name?: string;
    cnpj?: string;
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
  return fetchStudiesPage(token, { signal });
}

export async function fetchStudiesPage(
  token: string,
  options?: {
    page?: number;
    pageSize?: number;
    signal?: AbortSignal;
  },
) {
  const params = new URLSearchParams();
  if (options?.page && options.page > 0) {
    params.set("page", String(options.page));
  }
  if (options?.pageSize && options.pageSize > 0) {
    params.set("page_size", String(options.pageSize));
  }
  const query = params.toString();

  return apiRequest<PaginatedResponse<Study>>(
    `/api/studies/${query ? `?${query}` : ""}`,
    {
      token,
      signal: options?.signal,
    },
  );
}

export async function fetchInferenceJobs(
  token: string,
  signal?: AbortSignal,
) {
  return fetchInferenceJobsPage(token, { signal });
}

export async function fetchInferenceJobsPage(
  token: string,
  options?: {
    page?: number;
    pageSize?: number;
    signal?: AbortSignal;
  },
) {
  const params = new URLSearchParams();
  if (options?.page && options.page > 0) {
    params.set("page", String(options.page));
  }
  if (options?.pageSize && options.pageSize > 0) {
    params.set("page_size", String(options.pageSize));
  }
  const query = params.toString();

  return apiRequest<InferenceJobListResponse>(
    `/api/inference/jobs/${query ? `?${query}` : ""}`,
    {
      token,
      signal: options?.signal,
    },
  );
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

export async function deleteStudy(token: string, studyId: string) {
  return apiRequest<{ detail: string; deleted_artifacts?: number; failed_artifacts?: number }>(
    `/api/studies/${studyId}/`,
    {
      method: "DELETE",
      token,
    },
  );
}

export async function uploadStudy(token: string, input: StudyUploadInput) {
  return apiRequest<Study>("/api/studies/upload/", {
    method: "POST",
    token,
    body: buildStudyUploadFormData(input),
  });
}

export async function createInferenceJob(
  token: string,
  input: InferenceJobCreateInput,
  idempotencyKey?: string,
) {
  const headers: Record<string, string> = {};
  if (idempotencyKey) {
    headers["Idempotency-Key"] = idempotencyKey;
  }

  return apiRequest<InferenceJobCreateResponse>("/api/inference/jobs/", {
    method: "POST",
    token,
    headers,
    body: JSON.stringify({
      file_name: input.fileName,
      file_size: input.fileSize,
      content_type: input.contentType || "application/octet-stream",
      case_identification: input.caseIdentification || "",
      patient_name: input.patientName || "",
      age: input.age,
      exam_source: input.examSource || "",
      exam_modality: input.examModality || "",
      category_id: input.categoryId || "",
      requested_device: input.requestedDevice || "cuda",
      slice_batch_size: input.sliceBatchSize,
      correlation_id: input.correlationId,
    }),
  });
}

export async function uploadFileDirectToS3(
  upload: InferenceJobCreateResponse["upload"],
  file: File,
) {
  const formData = new FormData();
  Object.entries(upload.fields || {}).forEach(([key, value]) => {
    formData.append(key, value);
  });
  formData.append("file", file);

  const response = await fetch(upload.url, {
    method: "POST",
    body: formData,
  });

  if (!response.ok) {
    const errorBody = await response.text().catch(() => "");
    throw new Error(
      `Falha no upload para S3 (${response.status}): ${errorBody || response.statusText}`,
    );
  }
}

export async function completeInferenceJobUpload(
  token: string,
  jobId: string,
  payload: {
    inputArtifactId?: string;
    key?: string;
    sizeBytes?: number;
    etag?: string;
  },
) {
  return apiRequest<InferenceJobStatus>(
    `/api/inference/jobs/${jobId}/upload-complete/`,
    {
      method: "POST",
      token,
      body: JSON.stringify({
        input_artifact_id: payload.inputArtifactId,
        key: payload.key,
        size_bytes: payload.sizeBytes,
        etag: payload.etag,
      }),
    },
  );
}

export async function fetchInferenceJobStatus(
  token: string,
  jobId: string,
  signal?: AbortSignal,
) {
  return apiRequest<InferenceJobStatus>(`/api/inference/jobs/${jobId}/status/`, {
    token,
    signal,
  });
}

export async function fetchInferenceJobOutputs(
  token: string,
  jobId: string,
  signal?: AbortSignal,
) {
  return apiRequest<InferenceJobOutputsResponse>(
    `/api/inference/jobs/${jobId}/outputs/`,
    {
      token,
      signal,
    },
  );
}

export async function presignInferenceOutputDownload(
  token: string,
  jobId: string,
  outputId: string,
) {
  return apiRequest<InferenceOutputPresignResponse>(
    `/api/inference/jobs/${jobId}/outputs/${outputId}/presign-download/`,
    {
      method: "POST",
      token,
      body: JSON.stringify({}),
    },
  );
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
  try {
    const payload = await apiRequest<StudyResult>(`/api/studies/${studyId}/result/`, {
      token,
      signal,
    });
    const descriptiveAnalysis = String(payload.descriptive_analysis ?? "").trim();
    console.info("[GeminiDebug] fetchStudyResult:success", {
      studyId,
      hasDescriptiveAnalysis: Boolean(descriptiveAnalysis),
      descriptiveAnalysisLength: descriptiveAnalysis.length,
      segmentsLegendCount: Array.isArray(payload.segments_legend)
        ? payload.segments_legend.length
        : 0,
    });
    return payload;
  } catch (error) {
    console.error("[GeminiDebug] fetchStudyResult:error", {
      studyId,
      error: error instanceof Error ? error.message : String(error),
    });
    throw error;
  }
}

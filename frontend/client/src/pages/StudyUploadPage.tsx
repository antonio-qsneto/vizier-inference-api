import { FormEvent, useCallback, useEffect, useState } from "react";
import { Link, useLocation } from "wouter";
import { motion } from "framer-motion";
import { toast } from "sonner";
import {
  completeInferenceJobUpload,
  createInferenceJob,
  fetchCategories,
  uploadFileDirectToS3,
  uploadStudy,
} from "@/api/services";
import { useAuth } from "@/auth/AuthContext";
import {
  InlineNotice,
  LoadingState,
  PageIntro,
  Panel,
} from "@/components/primitives";
import { Spinner } from "@/components/ui/spinner";
import type { CategoriesCatalog, StudyIngestionReport } from "@/types/api";
import { env } from "@/env";

interface UploadFormState {
  caseIdentification: string;
  patientName: string;
  age: string;
  examSource: string;
  examModality: string;
  categoryId: string;
  file: File | null;
}

const defaultFormState: UploadFormState = {
  caseIdentification: "",
  patientName: "",
  age: "",
  examSource: "",
  examModality: "",
  categoryId: "",
  file: null,
};

function toTitleCase(value: string) {
  return value
    .split(" ")
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function formatTargetGroupLabel(modality: string, groupId: string) {
  if (modality === "MRI" && groupId === "head_tumor_cerebral") {
    return "Cabeça - Tumor cerebral";
  }
  if (modality === "MRI" && groupId === "head_esclerose_multipla") {
    return "Cabeça - Esclerose múltipla";
  }

  return toTitleCase(groupId.replace(/[_-]+/g, " "));
}

function formatTargetGroupLabelWithPrompt(
  modality: string,
  groupId: string,
  catalog: CategoriesCatalog,
) {
  const explicit = formatTargetGroupLabel(modality, groupId);
  if (
    explicit === "Cabeça - Tumor cerebral" ||
    explicit === "Cabeça - Esclerose múltipla"
  ) {
    return explicit;
  }

  const prompts = catalog[modality]?.[groupId] || [];
  if (prompts.length === 1) {
    return prompts[0];
  }
  return explicit;
}

function buildDicomIngestionMessage(report: StudyIngestionReport | null | undefined) {
  if (!report) {
    return null;
  }

  const source = String(report.source || "");
  if (!source.startsWith("dicom_")) {
    return null;
  }

  const details: string[] = [];
  const selectedSeries = String(report.selected_series_label || "").trim();
  if (selectedSeries) {
    details.push(`série: ${selectedSeries}`);
  }
  if (typeof report.effective_slices === "number" && report.effective_slices > 0) {
    details.push(`slices: ${report.effective_slices}`);
  }
  if (
    typeof report.candidate_series_count === "number" &&
    report.candidate_series_count > 1
  ) {
    details.push(`candidatas: ${report.candidate_series_count}`);
  }

  if (!details.length) {
    return "DICOM processado com seleção automática de série.";
  }
  return `DICOM processado (${details.join(" · ")})`;
}

export default function StudyUploadPage() {
  const [, navigate] = useLocation();
  const { accessToken, user } = useAuth();
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [catalog, setCatalog] = useState<CategoriesCatalog>({});
  const [error, setError] = useState<string | null>(null);
  const [formState, setFormState] = useState(defaultFormState);

  const loadCatalog = useCallback(async () => {
    if (!accessToken) {
      return;
    }

    setLoading(true);
    try {
      const nextCatalog = await fetchCategories(accessToken);
      setCatalog(nextCatalog);
      setError(null);
    } catch (requestError) {
      if (requestError instanceof Error) {
        setError(requestError.message);
      }
    } finally {
      setLoading(false);
    }
  }, [accessToken]);

  useEffect(() => {
    void loadCatalog();
  }, [loadCatalog]);

  const modalities = Object.keys(catalog);
  const targetGroups = formState.examModality
    ? Object.keys(catalog[formState.examModality] || {})
    : [];
  const includedTargets =
    formState.examModality && formState.categoryId
      ? catalog[formState.examModality]?.[formState.categoryId] || []
      : [];
  const effectiveRole =
    user?.effective_role ||
    (user?.role === "CLINIC_ADMIN"
      ? "clinic_admin"
      : user?.role === "CLINIC_DOCTOR"
        ? "clinic_doctor"
        : "individual");
  const isClinicAdmin = effectiveRole === "clinic_admin";
  const uploadEnabled = Boolean(user?.upload_enabled);
  const canUpgradeIndividually =
    effectiveRole === "individual" && !user?.clinic_id;

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (isClinicAdmin) {
      toast.error("Admins de clínica não possuem permissão de upload.");
      return;
    }
    if (!uploadEnabled) {
      if (canUpgradeIndividually) {
        toast.error("Upload indisponível. Faça upgrade na assinatura.");
        navigate("/billing");
      } else {
        toast.error("Upload indisponível para o estado atual da conta.");
      }
      return;
    }

    if (!accessToken || !formState.file) {
      toast.error("Selecione um arquivo suportado antes de enviar");
      return;
    }

    const ageValue = Number(formState.age);
    if (!Number.isFinite(ageValue) || ageValue < 0) {
      toast.error("A idade deve ser um número válido e positivo");
      return;
    }

    setSubmitting(true);
    try {
      if (env.useAsyncS3Upload) {
        const correlationId = crypto.randomUUID();
        const createResponse = await createInferenceJob(
          accessToken,
          {
            fileName: formState.file.name,
            fileSize: formState.file.size,
            contentType: formState.file.type || "application/octet-stream",
            caseIdentification: formState.caseIdentification.trim(),
            patientName: formState.patientName.trim(),
            age: ageValue,
            examSource: formState.examSource.trim(),
            examModality: formState.examModality,
            categoryId: formState.categoryId,
            correlationId,
          },
          correlationId,
        );

        await uploadFileDirectToS3(createResponse.upload, formState.file);
        await completeInferenceJobUpload(accessToken, createResponse.job_id, {
          inputArtifactId: createResponse.upload.input_artifact_id,
          key: createResponse.upload.key,
          sizeBytes: formState.file.size,
        });

        toast.success("Job de inferência enviado");
        navigate(`/studies/${createResponse.job_id}?async=1`);
      } else {
        const study = await uploadStudy(accessToken, {
          file: formState.file,
          caseIdentification: formState.caseIdentification.trim(),
          patientName: formState.patientName.trim(),
          age: ageValue,
          examSource: formState.examSource.trim(),
          examModality: formState.examModality,
          categoryId: formState.categoryId,
        });
        toast.success("Estudo enviado");
        const ingestionMessage = buildDicomIngestionMessage(study.ingestion_report);
        if (ingestionMessage) {
          toast.message(ingestionMessage);
        }
        navigate(`/studies/${study.id}`);
      }
    } catch (requestError) {
      toast.error(
        requestError instanceof Error
          ? requestError.message
          : "Falha no upload do estudo",
      );
    } finally {
      setSubmitting(false);
    }
  }

  if (loading) {
    return <LoadingState label="Carregando catálogo de modalidades..." />;
  }

  return (
    <motion.section
      initial={{ opacity: 0, y: 18 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35 }}
      className="space-y-6"
    >
      <PageIntro
        eyebrow="Envio"
        title="Enviar estudo para a pipeline de inferência"
        description="Envie um estudo para processamento assíncrono."
      />

      {isClinicAdmin ? (
        <InlineNotice title="Upload bloqueado para administrador">
          O perfil `CLINIC_ADMIN` é apenas gerencial e não pode enviar estudos.
        </InlineNotice>
      ) : null}

      {!isClinicAdmin && !uploadEnabled ? (
        <InlineNotice title="Upload bloqueado">
          {canUpgradeIndividually ? (
            <>
              Para enviar estudos, assine o plano individual mensal ou anual na
              página de assinatura.
              <span className="ml-2 inline-flex">
                <Link href="/billing">
                  <a className="font-semibold text-sky-300 underline underline-offset-4">
                    Ir para assinatura
                  </a>
                </Link>
              </span>
            </>
          ) : (
            <>Seu perfil não possui upload habilitado neste momento.</>
          )}
        </InlineNotice>
      ) : null}

      {error ? (
        <InlineNotice title="Falha ao carregar catálogo">{error}</InlineNotice>
      ) : null}

      {!isClinicAdmin && uploadEnabled ? (
        <form
          onSubmit={handleSubmit}
          className="grid gap-6 xl:grid-cols-[1.1fr_0.9fr]"
        >
        <Panel className="space-y-5">
          <div className="grid gap-4 md:grid-cols-2">
            <input
              value={formState.caseIdentification}
              onChange={(event) =>
                setFormState((current) => ({
                  ...current,
                  caseIdentification: event.target.value,
                }))
              }
              placeholder="CASE-2026-001"
              className="rounded-2xl border border-white/10 bg-white/6 px-4 py-3 text-sm text-white outline-none placeholder:text-slate-500 focus:border-sky-300/50"
            />
            <input
              value={formState.patientName}
              onChange={(event) =>
                setFormState((current) => ({
                  ...current,
                  patientName: event.target.value,
                }))
              }
              placeholder="Nome do paciente"
              className="rounded-2xl border border-white/10 bg-white/6 px-4 py-3 text-sm text-white outline-none placeholder:text-slate-500 focus:border-sky-300/50"
            />
            <input
              value={formState.age}
              onChange={(event) =>
                setFormState((current) => ({
                  ...current,
                  age: event.target.value,
                }))
              }
              type="number"
              min={0}
              max={130}
              placeholder="Idade"
              className="rounded-2xl border border-white/10 bg-white/6 px-4 py-3 text-sm text-white outline-none placeholder:text-slate-500 focus:border-sky-300/50"
            />
            <input
              value={formState.examSource}
              onChange={(event) =>
                setFormState((current) => ({
                  ...current,
                  examSource: event.target.value,
                }))
              }
              placeholder="Origem do exame"
              className="rounded-2xl border border-white/10 bg-white/6 px-4 py-3 text-sm text-white outline-none placeholder:text-slate-500 focus:border-sky-300/50"
            />
          </div>

          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <label className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-400">
                Modalidade do exame
              </label>
              <select
                value={formState.examModality}
                onChange={(event) =>
                  setFormState((current) => ({
                    ...current,
                    examModality: event.target.value,
                    categoryId: "",
                  }))
                }
                className="w-full rounded-2xl border border-white/10 bg-white/6 px-4 py-3 text-sm text-white outline-none focus:border-sky-300/50"
              >
                <option value="" className="bg-slate-900">
                  Selecione a modalidade
                </option>
                {modalities.map((modality) => (
                  <option
                    key={modality}
                    value={modality}
                    className="bg-slate-900"
                  >
                    {modality}
                  </option>
                ))}
              </select>
            </div>
            <div className="space-y-2">
              <label className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-400">
                Grupo-alvo
              </label>
              <select
                value={formState.categoryId}
                disabled={!formState.examModality}
                onChange={(event) =>
                  setFormState((current) => ({
                    ...current,
                    categoryId: event.target.value,
                  }))
                }
                className="w-full rounded-2xl border border-white/10 bg-white/6 px-4 py-3 text-sm text-white outline-none focus:border-sky-300/50 disabled:cursor-not-allowed disabled:opacity-50"
              >
                <option value="" className="bg-slate-900">
                  Selecione o grupo
                </option>
                {targetGroups.map((group) => (
                  <option key={group} value={group} className="bg-slate-900">
                    {formatTargetGroupLabelWithPrompt(
                      formState.examModality,
                      group,
                      catalog,
                    )}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <label className="block rounded-[28px] border border-dashed border-white/15 bg-white/5 p-6">
            <span className="text-sm font-semibold text-white">
              Envie ZIP, NPZ ou NIfTI (.nii / .nii.gz)
            </span>
            <p className="mt-2 text-sm leading-7 text-slate-300">
              Para DICOM, envie `.zip` (não `.dcm` isolado). O backend tenta ler
              layout canônico e também estrutura de pastas não canônica, com
              seleção automática da série volumétrica.
            </p>
            <p className="mt-2 text-xs leading-6 text-slate-400">
              Se houver múltiplas fases/séries no mesmo ZIP, compacte apenas a
              série clínica desejada para evitar seleção automática incorreta.
            </p>
            <input
              type="file"
              accept=".zip,.npz,.nii,.nii.gz"
              onChange={(event) =>
                setFormState((current) => ({
                  ...current,
                  file: event.target.files?.[0] ?? null,
                }))
              }
              className="mt-4 block w-full text-sm text-slate-300 file:mr-4 file:rounded-full file:border-0 file:bg-sky-500 file:px-4 file:py-2 file:font-semibold file:text-white"
            />
            {formState.file ? (
              <p className="mt-4 text-sm text-sky-100">{formState.file.name}</p>
            ) : null}
            {formState.file?.name.toLowerCase().endsWith(".zip") ? (
              <p className="mt-2 text-xs leading-6 text-slate-400">
                ZIP detectado: serão priorizadas séries com maior volume, `ORIGINAL`
                e menor espaçamento entre slices.
              </p>
            ) : null}
          </label>

          <button
            type="submit"
            disabled={submitting || !uploadEnabled}
            className="inline-flex items-center justify-center gap-2 rounded-2xl bg-sky-500 px-5 py-3 text-sm font-semibold text-white transition hover:bg-sky-400 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {submitting ? <Spinner className="size-4" /> : null}
            {submitting ? "Enviando estudo..." : "Enviar estudo"}
          </button>
        </Panel>

        <div className="space-y-6">
          <Panel className="space-y-4">
            <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-400">
              Alvos de segmentação incluídos
            </p>
            {includedTargets.length ? (
              <div className="flex flex-wrap gap-2">
                {includedTargets.map((target) => (
                  <span
                    key={target}
                    className="rounded-full border border-sky-300/20 bg-sky-500/10 px-3 py-1 text-xs font-semibold uppercase tracking-[0.12em] text-sky-100"
                  >
                    {target}
                  </span>
                ))}
              </div>
            ) : (
              <p className="text-sm leading-7 text-slate-300">
                Selecione modalidade e grupo para visualizar os alvos de segmentação.
              </p>
            )}
          </Panel>
        </div>
        </form>
      ) : null}
    </motion.section>
  );
}

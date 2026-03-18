import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "wouter";
import { motion } from "framer-motion";
import {
  fetchInferenceJobOutputs,
  fetchInferenceJobStatus,
  fetchStudy,
  fetchStudyResult,
  fetchStudyStatus,
  presignInferenceOutputDownload,
} from "@/api/services";
import { useAuth } from "@/auth/AuthContext";
import {
  InlineNotice,
  LoadingState,
  PageIntro,
  Panel,
  StatusPill,
} from "@/components/primitives";
import {
  isTerminalStudyStatus,
  useStudyStatusPolling,
} from "@/hooks/useStudyStatusPolling";
import { formatDateTime, formatPercentage } from "@/lib/format";
import { env } from "@/env";
import type {
  InferenceJobStatus,
  InferenceOutputArtifact,
  Study,
  StudyResult,
  StudyStatus,
} from "@/types/api";

interface AsyncOutputLink {
  output: InferenceOutputArtifact;
  url: string;
  expiresIn: number;
}

const asyncOutputKindLabels: Record<string, string> = {
  ORIGINAL_NIFTI: "Volume original (NIfTI)",
  MASK_NIFTI: "Máscara de segmentação (NIfTI)",
  SUMMARY_JSON: "Resumo da inferência (JSON)",
  NORMALIZED_INPUT_NPZ: "Input normalizado (NPZ)",
};

function isAsyncTerminalStatus(status?: string | null) {
  return status === "COMPLETED" || status === "FAILED";
}

function getAsyncJobDisplayTitle(status: InferenceJobStatus) {
  const payload =
    status.request_payload && typeof status.request_payload === "object"
      ? (status.request_payload as Record<string, unknown>)
      : {};

  const caseIdentification = String(payload.case_identification || "").trim();
  if (caseIdentification) {
    return caseIdentification;
  }

  const patientName = String(payload.patient_name || "").trim();
  if (patientName) {
    return patientName;
  }

  return "Estudo assíncrono";
}

function getOutputKindLabel(kind: string) {
  return asyncOutputKindLabels[kind] || kind.replaceAll("_", " ");
}

export default function StudyDetailPage({ studyId }: { studyId: string }) {
  const { accessToken } = useAuth();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [study, setStudy] = useState<Study | null>(null);
  const [statusSnapshot, setStatusSnapshot] = useState<StudyStatus | null>(null);
  const [result, setResult] = useState<StudyResult | null>(null);

  const [asyncStatus, setAsyncStatus] = useState<InferenceJobStatus | null>(null);
  const [asyncOutputs, setAsyncOutputs] = useState<AsyncOutputLink[]>([]);

  const isAsyncFlow = useMemo(() => {
    if (!env.useAsyncS3Upload || typeof window === "undefined") {
      return false;
    }
    return new URLSearchParams(window.location.search).get("async") === "1";
  }, []);

  const loadAsyncOutputs = useCallback(async () => {
    if (!accessToken || !studyId) {
      return;
    }

    const outputsPayload = await fetchInferenceJobOutputs(accessToken, studyId);
    const links = await Promise.all(
      outputsPayload.outputs.map(async (output) => {
        const signed = await presignInferenceOutputDownload(
          accessToken,
          studyId,
          output.id,
        );
        return {
          output,
          url: signed.url,
          expiresIn: signed.expires_in,
        };
      }),
    );
    setAsyncOutputs(links);
  }, [accessToken, studyId]);

  const loadData = useCallback(async () => {
    if (!accessToken) {
      return;
    }

    setLoading(true);
    try {
      if (isAsyncFlow) {
        const payload = await fetchInferenceJobStatus(accessToken, studyId);
        setAsyncStatus(payload);
        if (payload.status === "COMPLETED") {
          await loadAsyncOutputs();
        }
      } else {
        const studyPayload = await fetchStudy(accessToken, studyId);
        const statusPayload = isTerminalStudyStatus(studyPayload.status)
          ? null
          : await fetchStudyStatus(accessToken, studyId);
        setStudy(studyPayload);
        setStatusSnapshot(statusPayload);
      }
      setError(null);
    } catch (requestError) {
      if (requestError instanceof Error) {
        setError(requestError.message);
      }
    } finally {
      setLoading(false);
    }
  }, [accessToken, isAsyncFlow, loadAsyncOutputs, studyId]);

  useEffect(() => {
    void loadData();
  }, [loadData]);

  // Legacy study polling
  const polling = useStudyStatusPolling({
    studyId,
    token: accessToken,
    initialValue: statusSnapshot,
    enabled:
      !isAsyncFlow &&
      Boolean(statusSnapshot && !isTerminalStudyStatus(statusSnapshot.status)),
  });

  useEffect(() => {
    if (isAsyncFlow) {
      return;
    }
    const nextStatus = polling.value;
    if (!nextStatus) {
      return;
    }

    setStatusSnapshot(nextStatus);
    setStudy((currentStudy) => {
      if (!currentStudy) {
        return currentStudy;
      }

      return {
        ...currentStudy,
        status: nextStatus.status,
        updated_at: nextStatus.updated_at,
        job: currentStudy.job
          ? {
              ...currentStudy.job,
              status: nextStatus.job_status || currentStudy.job.status,
              progress_percent:
                nextStatus.job_progress ?? currentStudy.job.progress_percent,
            }
          : currentStudy.job,
      };
    });
  }, [isAsyncFlow, polling.value]);

  // Async job polling
  useEffect(() => {
    if (!isAsyncFlow || !accessToken || !asyncStatus) {
      return;
    }
    if (isAsyncTerminalStatus(asyncStatus.status)) {
      return;
    }

    const timer = window.setInterval(async () => {
      try {
        const next = await fetchInferenceJobStatus(accessToken, studyId);
        setAsyncStatus(next);
        if (next.status === "COMPLETED") {
          await loadAsyncOutputs();
        }
      } catch (requestError) {
        if (requestError instanceof Error) {
          setError(requestError.message);
        }
      }
    }, 5000);

    return () => window.clearInterval(timer);
  }, [accessToken, asyncStatus, isAsyncFlow, loadAsyncOutputs, studyId]);

  const loadResult = useCallback(async () => {
    if (!accessToken || !studyId || isAsyncFlow) {
      return;
    }

    try {
      const payload = await fetchStudyResult(accessToken, studyId);
      setResult(payload);
    } catch {
      setResult(null);
    }
  }, [accessToken, isAsyncFlow, studyId]);

  useEffect(() => {
    if (!isAsyncFlow && (statusSnapshot?.status || study?.status) === "COMPLETED") {
      void loadResult();
    }
  }, [isAsyncFlow, loadResult, statusSnapshot?.status, study?.status]);

  if (loading) {
    return <LoadingState label="Carregando estudo..." />;
  }

  if (isAsyncFlow) {
    if (!asyncStatus) {
      return (
        <InlineNotice title="Inference job not found" tone="danger">
          {error || "The inference job could not be loaded."}
        </InlineNotice>
      );
    }

    return (
      <motion.section
        initial={{ opacity: 0, y: 18 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.35 }}
        className="space-y-6"
      >
        <PageIntro
          eyebrow="Inferência assíncrona"
          title={getAsyncJobDisplayTitle(asyncStatus)}
          description="Fluxo assíncrono com upload direto no S3 e processamento em fila."
          actions={
            <div className="flex gap-3">
              <button
                type="button"
                onClick={() => void loadData()}
                className="rounded-full border border-white/10 bg-white/6 px-4 py-2 text-sm font-semibold text-slate-100 transition hover:bg-white/10"
              >
                Atualizar
              </button>
              {asyncStatus.status === "COMPLETED" ? (
                <Link href={`/studies/${asyncStatus.id}/viewer?async=1`}>
                  <a className="rounded-full bg-sky-500 px-4 py-2 text-sm font-semibold text-white transition hover:bg-sky-400">
                    Abrir visualizador
                  </a>
                </Link>
              ) : null}
            </div>
          }
        />

        {error ? <InlineNotice title="Job request failed">{error}</InlineNotice> : null}

        <Panel className="space-y-5">
          <div className="flex flex-wrap items-center gap-3">
            <StatusPill status={asyncStatus.status} />
          </div>
          <div>
            <div className="flex items-center justify-between text-xs uppercase tracking-[0.16em] text-slate-400">
              <span>Progress</span>
              <span>{formatPercentage(asyncStatus.progress_percent || 0)}</span>
            </div>
            <div className="mt-3 h-3 overflow-hidden rounded-full bg-white/8">
              <div
                className="h-full rounded-full bg-[linear-gradient(90deg,#0195f8,#38bdf8)] transition-all"
                style={{
                  width: `${Math.min(Math.max(asyncStatus.progress_percent || 0, 0), 100)}%`,
                }}
              />
            </div>
          </div>
          <div className="grid gap-3 md:grid-cols-2">
            <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
              <p className="text-xs uppercase tracking-[0.18em] text-slate-400">Created</p>
              <p className="mt-2 text-sm font-semibold text-white">{formatDateTime(asyncStatus.created_at)}</p>
            </div>
            <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
              <p className="text-xs uppercase tracking-[0.18em] text-slate-400">Updated</p>
              <p className="mt-2 text-sm font-semibold text-white">{formatDateTime(asyncStatus.updated_at)}</p>
            </div>
          </div>

          {asyncStatus.error_message ? (
            <InlineNotice title="Processing error" tone="danger">
              {asyncStatus.error_message}
            </InlineNotice>
          ) : null}
        </Panel>

        <Panel className="space-y-4">
          <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-400">
            Arquivos de saída
          </p>
          {asyncOutputs.length ? (
            <div className="space-y-3">
              {asyncOutputs.map((item) => (
                <a
                  key={item.output.id}
                  href={item.url}
                  target="_blank"
                  rel="noreferrer"
                  className="block rounded-2xl border border-white/10 bg-white/5 px-4 py-3 text-sm text-white hover:bg-white/10"
                >
                  {getOutputKindLabel(item.output.kind)}
                </a>
              ))}
            </div>
          ) : (
            <p className="text-sm leading-7 text-slate-300">
              Os arquivos aparecerão após o status `COMPLETED`.
            </p>
          )}
        </Panel>
      </motion.section>
    );
  }

  if (!study) {
    return (
      <InlineNotice title="Study not found" tone="danger">
        {error || "The backend did not return the requested study."}
      </InlineNotice>
    );
  }

  const currentStatus = statusSnapshot?.status || study.status;
  const jobProgress = statusSnapshot?.job_progress ?? study.job?.progress_percent ?? 0;

  return (
    <motion.section
      initial={{ opacity: 0, y: 18 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35 }}
      className="space-y-6"
    >
      <PageIntro
        eyebrow="Study detail"
        title={study.case_identification || study.patient_name || "Estudo clínico"}
        description="Detalhe do estudo com polling em `/status/`, metadata do upload e acesso ao viewer quando o backend finalizar o processamento."
        actions={
          <div className="flex gap-3">
            <button
              type="button"
              onClick={() => void loadData()}
              className="rounded-full border border-white/10 bg-white/6 px-4 py-2 text-sm font-semibold text-slate-100 transition hover:bg-white/10"
            >
              Atualizar
            </button>
            {currentStatus === "COMPLETED" ? (
              <Link href={`/studies/${study.id}/viewer`}>
                <a className="rounded-full bg-sky-500 px-4 py-2 text-sm font-semibold text-white transition hover:bg-sky-400">
                  Abrir visualizador
                </a>
              </Link>
            ) : null}
          </div>
        }
      />

      {error ? <InlineNotice title="Study request failed">{error}</InlineNotice> : null}
      {polling.error ? <InlineNotice title="Status polling failed">{polling.error}</InlineNotice> : null}

      <div className="grid gap-6 xl:grid-cols-[0.85fr_1.15fr]">
        <Panel className="space-y-5">
          <div className="flex flex-wrap items-center gap-3">
            <StatusPill status={currentStatus} />
            <p className="text-sm text-slate-300">
              Processamento {statusSnapshot?.job_status || study.job?.status || "UNKNOWN"}
            </p>
          </div>
          <div className="space-y-2">
            <p className="text-sm leading-7 text-slate-300">
              {study.exam_modality || "Unknown modality"} · {study.category}
            </p>
            <p className="text-sm leading-7 text-slate-300">
              Source: {study.exam_source || "N/A"} · Owner: {study.owner_email}
            </p>
          </div>
          <div>
            <div className="flex items-center justify-between text-xs uppercase tracking-[0.16em] text-slate-400">
              <span>Progress</span>
              <span>{formatPercentage(jobProgress)}</span>
            </div>
            <div className="mt-3 h-3 overflow-hidden rounded-full bg-white/8">
              <div
                className="h-full rounded-full bg-[linear-gradient(90deg,#0195f8,#38bdf8)] transition-all"
                style={{ width: `${Math.min(Math.max(jobProgress, 0), 100)}%` }}
              />
            </div>
          </div>
          {study.error_message ? (
            <InlineNotice title="Processing error" tone="danger">
              {study.error_message}
            </InlineNotice>
          ) : null}
        </Panel>

        <div className="space-y-6">
          <Panel className="space-y-4">
            <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-400">
              Timeline
            </p>
            <div className="grid gap-3 md:grid-cols-2">
              {[
                { label: "Created", value: formatDateTime(study.created_at) },
                { label: "Updated", value: formatDateTime(study.updated_at) },
                { label: "Completed", value: formatDateTime(study.completed_at) },
              ].map((entry) => (
                <div
                  key={entry.label}
                  className="rounded-2xl border border-white/10 bg-white/5 p-4"
                >
                  <p className="text-xs uppercase tracking-[0.18em] text-slate-400">
                    {entry.label}
                  </p>
                  <p className="mt-2 text-sm font-semibold text-white">{entry.value}</p>
                </div>
              ))}
            </div>
          </Panel>

          <Panel className="space-y-4">
            <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-400">
              Result summary
            </p>
            {result ? (
              <div className="space-y-3">
                <p className="text-sm leading-7 text-slate-300">
                  Assets ready: {result.image_file_name} and {result.mask_file_name}
                </p>
                {result.segments_legend.length ? (
                  <div className="space-y-3">
                    {result.segments_legend.slice(0, 6).map((segment) => (
                      <div
                        key={segment.id}
                        className="rounded-2xl border border-white/10 bg-white/5 px-4 py-3"
                      >
                        <div className="flex items-center gap-3">
                          <span
                            className="inline-flex h-3 w-3 rounded-full"
                            style={{ backgroundColor: segment.color }}
                          />
                          <p className="text-sm font-semibold text-white">
                            {segment.label}
                          </p>
                        </div>
                        <p className="mt-2 text-sm text-slate-300">
                          {segment.voxels.toLocaleString()} voxels · {segment.percentage}%
                        </p>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="text-sm leading-7 text-slate-300">
                    O backend não retornou `segments_legend`, mas o viewer ainda
                    tentará carregar image e mask.
                  </p>
                )}
              </div>
            ) : currentStatus === "COMPLETED" ? (
              <p className="text-sm leading-7 text-slate-300">
                Resultado ainda não carregado. Tente atualizar ou abrir o viewer
                para forçar a resolução do endpoint `/result/`.
              </p>
            ) : (
              <p className="text-sm leading-7 text-slate-300">
                O resultado fica disponível quando o status finaliza em `COMPLETED`.
              </p>
            )}
          </Panel>
        </div>
      </div>
    </motion.section>
  );
}

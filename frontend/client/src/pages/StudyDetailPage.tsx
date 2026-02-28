import { useCallback, useEffect, useState } from "react";
import { Link } from "wouter";
import { motion } from "framer-motion";
import { fetchStudy, fetchStudyResult, fetchStudyStatus } from "@/api/services";
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
import type { Study, StudyResult, StudyStatus } from "@/types/api";

export default function StudyDetailPage({ studyId }: { studyId: string }) {
  const { accessToken } = useAuth();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [study, setStudy] = useState<Study | null>(null);
  const [statusSnapshot, setStatusSnapshot] = useState<StudyStatus | null>(null);
  const [result, setResult] = useState<StudyResult | null>(null);

  const loadStudy = useCallback(async () => {
    if (!accessToken) {
      return;
    }

    setLoading(true);
    try {
      const studyPayload = await fetchStudy(accessToken, studyId);
      const statusPayload = isTerminalStudyStatus(studyPayload.status)
        ? null
        : await fetchStudyStatus(accessToken, studyId);
      setStudy(studyPayload);
      setStatusSnapshot(statusPayload);
      setError(null);
    } catch (requestError) {
      if (requestError instanceof Error) {
        setError(requestError.message);
      }
    } finally {
      setLoading(false);
    }
  }, [accessToken, studyId]);

  useEffect(() => {
    void loadStudy();
  }, [loadStudy]);

  const polling = useStudyStatusPolling({
    studyId,
    token: accessToken,
    initialValue: statusSnapshot,
    enabled: Boolean(statusSnapshot && !isTerminalStudyStatus(statusSnapshot.status)),
  });

  useEffect(() => {
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
  }, [polling.value]);

  const loadResult = useCallback(async () => {
    if (!accessToken || !studyId) {
      return;
    }

    try {
      const payload = await fetchStudyResult(accessToken, studyId);
      setResult(payload);
    } catch {
      setResult(null);
    }
  }, [accessToken, studyId]);

  useEffect(() => {
    if ((statusSnapshot?.status || study?.status) === "COMPLETED") {
      void loadResult();
    }
  }, [loadResult, statusSnapshot?.status, study?.status]);

  if (loading) {
    return <LoadingState label="Carregando estudo..." />;
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
        title={study.case_identification || study.patient_name || study.id}
        description="Detalhe do estudo com polling em `/status/`, metadata do upload e acesso ao viewer quando o backend finalizar o processamento."
        actions={
          <div className="flex gap-3">
            <button
              type="button"
              onClick={() => void loadStudy()}
              className="rounded-full border border-white/10 bg-white/6 px-4 py-2 text-sm font-semibold text-slate-100 transition hover:bg-white/10"
            >
              Refresh
            </button>
            {currentStatus === "COMPLETED" ? (
              <Link href={`/studies/${study.id}/viewer`}>
                <a className="rounded-full bg-sky-500 px-4 py-2 text-sm font-semibold text-white transition hover:bg-sky-400">
                  Open viewer
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
              Job {statusSnapshot?.job_status || study.job?.status || "UNKNOWN"}
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
                {
                  label: "External job",
                  value: study.job?.external_job_id || "Not available",
                },
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

import { useCallback, useEffect, useState } from "react";
import { Link } from "wouter";
import { motion } from "framer-motion";
import { FolderOpen, RotateCcw } from "lucide-react";
import { fetchStudy, fetchStudyResult, fetchStudyStatus } from "@/api/services";
import { useAuth } from "@/auth/AuthContext";
import {
  InlineNotice,
  LoadingState,
  Panel,
  StatusPill,
} from "@/components/primitives";
import {
  isTerminalStudyStatus,
  useStudyStatusPolling,
} from "@/hooks/useStudyStatusPolling";
import { OrthogonalViewer } from "@/viewer/OrthogonalViewer";
import type { Study, StudyResult, StudyStatus } from "@/types/api";

export default function StudyViewerPage({ studyId }: { studyId: string }) {
  const { accessToken } = useAuth();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [study, setStudy] = useState<Study | null>(null);
  const [statusSnapshot, setStatusSnapshot] = useState<StudyStatus | null>(
    null,
  );
  const [result, setResult] = useState<StudyResult | null>(null);

  const loadViewerData = useCallback(async () => {
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
    void loadViewerData();
  }, [loadViewerData]);

  const polling = useStudyStatusPolling({
    studyId,
    token: accessToken,
    initialValue: statusSnapshot,
    enabled: Boolean(
      statusSnapshot && !isTerminalStudyStatus(statusSnapshot.status),
    ),
  });

  useEffect(() => {
    const nextStatus = polling.value;
    if (!nextStatus) {
      return;
    }

    setStatusSnapshot(nextStatus);
    setStudy((currentStudy) =>
      currentStudy
        ? {
            ...currentStudy,
            status: nextStatus.status,
            updated_at: nextStatus.updated_at,
          }
        : currentStudy,
    );
  }, [polling.value]);

  const loadResult = useCallback(async () => {
    if (!accessToken || !studyId) {
      return;
    }

    try {
      const payload = await fetchStudyResult(accessToken, studyId);
      setResult(payload);
      setError(null);
    } catch (requestError) {
      if (requestError instanceof Error) {
        setError(requestError.message);
      }
    }
  }, [accessToken, studyId]);

  useEffect(() => {
    if ((statusSnapshot?.status || study?.status) === "COMPLETED") {
      void loadResult();
    }
  }, [loadResult, statusSnapshot?.status, study?.status]);

  if (loading) {
    return <LoadingState label="Preparing viewer..." />;
  }

  if (!study) {
    return (
      <InlineNotice title="Study unavailable" tone="danger">
        {error || "The study could not be loaded from the backend."}
      </InlineNotice>
    );
  }

  const currentStatus = statusSnapshot?.status || study.status;

  return (
    <motion.section
      initial={{ opacity: 0, y: 18 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35 }}
      className="space-y-4"
    >
      <div className="flex flex-col gap-3 rounded-[10px] border border-white/8 bg-[#23252d] px-4 py-3 md:flex-row md:items-center md:justify-between">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <FolderOpen className="h-3.5 w-3.5 text-sky-300/80" />
            <p className="text-[11px] font-semibold uppercase tracking-[0.24em] text-sky-300/80">
              Viewer
            </p>
          </div>
          <h1 className="mt-1 truncate text-xl font-semibold tracking-tight text-white">
            {study.case_identification || study.patient_name || study.id}
          </h1>
          <p className="mt-1 text-sm text-slate-300">
            {study.exam_modality || "Unknown"} · {study.category}
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <StatusPill status={currentStatus} />
          <Link href={`/studies/${study.id}`}>
            <a className="inline-flex items-center gap-2 rounded-[8px] border border-white/10 bg-[#2a2c34] px-3 py-2 text-sm font-semibold text-slate-100 transition hover:bg-[#31343d]">
              <FolderOpen className="h-4 w-4" />
              Back to detail
            </a>
          </Link>
          <button
            type="button"
            onClick={() => void loadResult()}
            className="inline-flex items-center gap-2 rounded-[8px] border border-sky-300/30 bg-sky-500/15 px-3 py-2 text-sm font-semibold text-white transition hover:bg-sky-400/20"
          >
            <RotateCcw className="h-4 w-4" />
            Reload assets
          </button>
        </div>
      </div>

      {error ? (
        <InlineNotice title="Viewer request failed">{error}</InlineNotice>
      ) : null}
      {polling.error ? (
        <InlineNotice title="Status polling failed">
          {polling.error}
        </InlineNotice>
      ) : null}

      {currentStatus !== "COMPLETED" ? (
        <Panel className="space-y-4">
          <p className="text-lg font-semibold text-white">
            Viewer will unlock when processing completes
          </p>
          <p className="text-sm leading-7 text-slate-300">
            O endpoint `/result/` só fica disponível quando o estudo chega em
            `COMPLETED`. Enquanto isso, acompanhe o polling desta página ou
            volte para o detalhe do estudo.
          </p>
        </Panel>
      ) : result ? (
        <div className="-mx-4 md:-mx-6 lg:-mx-8">
          <OrthogonalViewer
            imageUrl={result.image_url}
            maskUrl={result.mask_url}
            modality={study.exam_modality}
            segmentsLegend={result.segments_legend}
          />
        </div>
      ) : (
        <Panel className="space-y-4">
          <p className="text-lg font-semibold text-white">
            Result assets not ready
          </p>
          <p className="text-sm leading-7 text-slate-300">
            O backend marcou o estudo como `COMPLETED`, mas o frontend ainda não
            conseguiu resolver `image_url` e `mask_url`. Tente recarregar os
            assets.
          </p>
        </Panel>
      )}
    </motion.section>
  );
}

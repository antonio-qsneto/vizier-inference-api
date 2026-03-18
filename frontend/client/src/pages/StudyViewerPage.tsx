import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "wouter";
import { motion } from "framer-motion";
import { FolderOpen, RotateCcw } from "lucide-react";
import {
  fetchCategories,
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
  Panel,
  StatusPill,
} from "@/components/primitives";
import {
  isTerminalStudyStatus,
  useStudyStatusPolling,
} from "@/hooks/useStudyStatusPolling";
import { env } from "@/env";
import { OrthogonalViewer } from "@/viewer/OrthogonalViewer";
import type {
  InferenceJobStatus,
  InferenceOutputArtifact,
  SegmentLegendItem,
  Study,
  StudyResult,
  StudyStatus,
} from "@/types/api";

interface AsyncViewerAssets {
  imageUrl: string | null;
  maskUrl: string | null;
  summaryUrl: string | null;
  segmentsLegend: SegmentLegendItem[];
  fallbackSegmentNames: string[];
  descriptiveAnalysis: string | null;
  availableOutputKinds: string[];
}

function isAsyncTerminalStatus(status?: string | null) {
  return status === "COMPLETED" || status === "FAILED";
}

function findOutputByKind(
  outputs: InferenceOutputArtifact[],
  kind: string,
  suffixes: string[] = [],
) {
  const kindMatch = outputs.find((output) => output.kind === kind);
  if (kindMatch) {
    return kindMatch;
  }

  const normalizedSuffixes = suffixes.map((suffix) => suffix.toLowerCase());
  return outputs.find((output) => {
    const lowerKey = output.key.toLowerCase();
    return normalizedSuffixes.some((suffix) => lowerKey.endsWith(suffix));
  });
}

const asyncLegendPalette = [
  "#0a84ff",
  "#f97316",
  "#22c55e",
  "#ec4899",
  "#eab308",
  "#8b5cf6",
  "#06b6d4",
  "#ef4444",
];

function buildLegendItem(
  raw: Record<string, unknown>,
  fallbackId: number,
): SegmentLegendItem {
  const normalizedId = Number(raw.id ?? raw.segment_id ?? raw.label_id ?? fallbackId);
  const id = Number.isFinite(normalizedId) && normalizedId > 0 ? normalizedId : fallbackId;
  const prompt = String(raw.prompt ?? raw.text_prompt ?? raw.query ?? "").trim();
  const labelSource = String(
    raw.label ??
      raw.name ??
      raw.title ??
      raw.class_name ??
      raw.class_label ??
      prompt ??
      "",
  ).trim();
  const label =
    labelSource && !/^label\s*\d+$/i.test(labelSource)
      ? labelSource
      : `Segment ${id}`;

  const voxelsRaw = Number(raw.voxels ?? raw.count ?? raw.pixels ?? 0);
  const voxels = Number.isFinite(voxelsRaw) && voxelsRaw >= 0 ? Math.round(voxelsRaw) : 0;

  const fractionRaw = Number(raw.fraction ?? 0);
  const fraction =
    Number.isFinite(fractionRaw) && fractionRaw >= 0 ? fractionRaw : 0;

  const percentageRaw = Number(raw.percentage ?? (fraction > 0 ? fraction * 100 : 0));
  const percentage =
    Number.isFinite(percentageRaw) && percentageRaw >= 0
      ? Number(percentageRaw.toFixed(2))
      : 0;

  const colorValue = String(raw.color ?? "").trim();
  const color =
    colorValue && /^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$/.test(colorValue)
      ? colorValue
      : asyncLegendPalette[(id - 1) % asyncLegendPalette.length];

  return {
    id,
    label,
    prompt,
    voxels,
    fraction,
    percentage,
    color,
  };
}

function getCategoryPromptsFromCatalog(
  catalog: Record<string, Record<string, string[]>>,
  examModality: string,
  categoryId: string,
) {
  const normalizedModality = examModality.trim().toLowerCase();
  const normalizedCategory = categoryId.trim().toLowerCase();
  if (!normalizedModality || !normalizedCategory) {
    return [];
  }

  const modalityKey = Object.keys(catalog).find(
    (key) => key.toLowerCase() === normalizedModality,
  );
  if (!modalityKey) {
    return [];
  }
  const categoryMap = catalog[modalityKey] || {};
  const categoryKey = Object.keys(categoryMap).find(
    (key) => key.toLowerCase() === normalizedCategory,
  );
  if (!categoryKey) {
    return [];
  }
  return (categoryMap[categoryKey] || []).map((item) => String(item || "").trim());
}

function parseAsyncSummaryLegend(summary: unknown): SegmentLegendItem[] {
  if (!summary || typeof summary !== "object" || Array.isArray(summary)) {
    return [];
  }

  const payload = summary as Record<string, unknown>;

  if (Array.isArray(payload.segments_legend)) {
    return payload.segments_legend
      .map((item, index) =>
        buildLegendItem(
          (item && typeof item === "object" && !Array.isArray(item)
            ? (item as Record<string, unknown>)
            : {}) as Record<string, unknown>,
          index + 1,
        ),
      )
      .sort((left, right) => left.id - right.id);
  }

  if (Array.isArray(payload.segments)) {
    return payload.segments
      .map((item, index) =>
        buildLegendItem(
          (item && typeof item === "object" && !Array.isArray(item)
            ? (item as Record<string, unknown>)
            : {}) as Record<string, unknown>,
          index + 1,
        ),
      )
      .sort((left, right) => left.id - right.id);
  }

  const mapLike = (payload.id_to_label || payload.labels) as
    | Record<string, unknown>
    | undefined;
  if (mapLike && typeof mapLike === "object" && !Array.isArray(mapLike)) {
    return Object.entries(mapLike)
      .map(([key, value], index) =>
        buildLegendItem(
          {
            id: Number(key),
            label: String(value ?? "").trim(),
          },
          index + 1,
        ),
      )
      .filter((item) => item.id > 0)
      .sort((left, right) => left.id - right.id);
  }

  return [];
}

function parseAsyncSummaryAnalysis(summary: unknown): string | null {
  if (!summary || typeof summary !== "object" || Array.isArray(summary)) {
    return null;
  }

  const payload = summary as Record<string, unknown>;
  const candidates = [
    payload.descriptive_analysis,
    payload.analysis,
    payload.summary_text,
    payload.report,
  ];

  for (const candidate of candidates) {
    const text = String(candidate ?? "").trim();
    if (text) {
      return text;
    }
  }

  return null;
}

function getAsyncViewerTitle(status: InferenceJobStatus) {
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

function getAsyncViewerPatientName(status: InferenceJobStatus) {
  const payload =
    status.request_payload && typeof status.request_payload === "object"
      ? (status.request_payload as Record<string, unknown>)
      : {};
  const patientName = String(payload.patient_name || "").trim();
  if (patientName) {
    return patientName;
  }
  return getAsyncViewerTitle(status);
}

function getAsyncViewerModality(status: InferenceJobStatus) {
  const payload =
    status.request_payload && typeof status.request_payload === "object"
      ? (status.request_payload as Record<string, unknown>)
      : {};
  return String(payload.exam_modality || "").trim();
}

function formatSegmentationTargets(labels: string[]) {
  const normalized = labels.map((item) => item.trim()).filter(Boolean);
  if (!normalized.length) {
    return "Não informado";
  }

  const maxVisible = 3;
  const visible = normalized.slice(0, maxVisible).join(", ");
  if (normalized.length <= maxVisible) {
    return visible;
  }

  return `${visible} +${normalized.length - maxVisible}`;
}

export default function StudyViewerPage({ studyId }: { studyId: string }) {
  const { accessToken } = useAuth();
  const isAsyncFlow = useMemo(() => {
    if (!env.useAsyncS3Upload || typeof window === "undefined") {
      return false;
    }
    return new URLSearchParams(window.location.search).get("async") === "1";
  }, []);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [study, setStudy] = useState<Study | null>(null);
  const [statusSnapshot, setStatusSnapshot] = useState<StudyStatus | null>(
    null,
  );
  const [result, setResult] = useState<StudyResult | null>(null);
  const [asyncStatus, setAsyncStatus] = useState<InferenceJobStatus | null>(
    null,
  );
  const [asyncAssets, setAsyncAssets] = useState<AsyncViewerAssets | null>(
    null,
  );

  const loadAsyncAssets = useCallback(async (statusPayload?: InferenceJobStatus | null) => {
    if (!accessToken) {
      return;
    }

    const outputsPayload = await fetchInferenceJobOutputs(accessToken, studyId);
    const outputs = outputsPayload.outputs || [];
    const imageOutput = findOutputByKind(outputs, "ORIGINAL_NIFTI", [
      "original_image.nii.gz",
      "image.nii.gz",
    ]);
    const maskOutput = findOutputByKind(outputs, "MASK_NIFTI", ["mask.nii.gz"]);
    const summaryOutput = findOutputByKind(outputs, "SUMMARY_JSON", [
      "summary.json",
    ]);

    if (!imageOutput || !maskOutput) {
      setAsyncAssets({
        imageUrl: null,
        maskUrl: null,
        summaryUrl: null,
        segmentsLegend: [],
        fallbackSegmentNames: [],
        descriptiveAnalysis: null,
        availableOutputKinds: outputs.map((output) => output.kind),
      });
      return;
    }

    const [imageSigned, maskSigned, summarySigned] = await Promise.all([
      presignInferenceOutputDownload(accessToken, studyId, imageOutput.id),
      presignInferenceOutputDownload(accessToken, studyId, maskOutput.id),
      summaryOutput
        ? presignInferenceOutputDownload(accessToken, studyId, summaryOutput.id)
        : Promise.resolve(null),
    ]);

    let segmentsLegend: SegmentLegendItem[] = [];
    let descriptiveAnalysis: string | null = null;
    let fallbackSegmentNames: string[] = [];

    if (summarySigned?.url) {
      try {
        const response = await fetch(summarySigned.url);
        if (response.ok) {
          const summaryPayload = await response.json();
          segmentsLegend = parseAsyncSummaryLegend(summaryPayload);
          descriptiveAnalysis = parseAsyncSummaryAnalysis(summaryPayload);
        }
      } catch {
        // Summary parsing is best-effort; viewer still works with fallback labels.
      }
    }

    if (!segmentsLegend.length && statusPayload?.request_payload) {
      const requestPayload = statusPayload.request_payload as Record<string, unknown>;
      const examModality = String(requestPayload.exam_modality || "").trim();
      const categoryId = String(requestPayload.category_id || "").trim();
      if (examModality && categoryId) {
        try {
          const catalog = await fetchCategories(accessToken);
          fallbackSegmentNames = getCategoryPromptsFromCatalog(
            catalog,
            examModality,
            categoryId,
          );
        } catch {
          fallbackSegmentNames = [];
        }
      }
    }

    setAsyncAssets({
      imageUrl: imageSigned.url,
      maskUrl: maskSigned.url,
      summaryUrl: summarySigned?.url || null,
      segmentsLegend,
      fallbackSegmentNames,
      descriptiveAnalysis,
      availableOutputKinds: outputs.map((output) => output.kind),
    });
  }, [accessToken, studyId]);

  const loadViewerData = useCallback(async () => {
    if (!accessToken) {
      return;
    }

    setLoading(true);
    try {
      if (isAsyncFlow) {
        const payload = await fetchInferenceJobStatus(accessToken, studyId);
        setAsyncStatus(payload);
        if (payload.status === "COMPLETED") {
          await loadAsyncAssets(payload);
        } else {
          setAsyncAssets(null);
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
  }, [accessToken, isAsyncFlow, loadAsyncAssets, studyId]);

  useEffect(() => {
    void loadViewerData();
  }, [loadViewerData]);

  const polling = useStudyStatusPolling({
    studyId,
    token: accessToken,
    initialValue: statusSnapshot,
    enabled: Boolean(
      !isAsyncFlow &&
        statusSnapshot &&
        !isTerminalStudyStatus(statusSnapshot.status),
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
          await loadAsyncAssets(next);
        }
      } catch (requestError) {
        if (requestError instanceof Error) {
          setError(requestError.message);
        }
      }
    }, 5000);

    return () => window.clearInterval(timer);
  }, [accessToken, asyncStatus, isAsyncFlow, loadAsyncAssets, studyId]);

  const loadResult = useCallback(async () => {
    if (!accessToken || !studyId || isAsyncFlow) {
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
  }, [accessToken, isAsyncFlow, studyId]);

  useEffect(() => {
    if (!isAsyncFlow && (statusSnapshot?.status || study?.status) === "COMPLETED") {
      void loadResult();
    }
  }, [isAsyncFlow, loadResult, statusSnapshot?.status, study?.status]);

  if (loading) {
    return <LoadingState label={isAsyncFlow ? "Preparing async viewer..." : "Preparing viewer..."} />;
  }

  if (isAsyncFlow) {
    if (!asyncStatus) {
      return (
        <InlineNotice title="Inference job unavailable" tone="danger">
          {error || "The inference job could not be loaded from the backend."}
        </InlineNotice>
      );
    }

    const currentAsyncStatus = asyncStatus.status;
    const asyncPatientName = getAsyncViewerPatientName(asyncStatus);
    const asyncModality = getAsyncViewerModality(asyncStatus);
    const asyncSegmentationTargets = formatSegmentationTargets(
      asyncAssets?.segmentsLegend?.length
        ? asyncAssets.segmentsLegend.map((segment) => segment.label)
        : asyncAssets?.fallbackSegmentNames || [],
    );

    return (
      <motion.section
        initial={{ opacity: 0, y: 18 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.35 }}
        className="space-y-4"
      >
        <div className="flex flex-col gap-3 rounded-[10px] border border-white/8 bg-[#23252d] px-4 py-3 md:flex-row md:items-center md:justify-between">
          <div className="min-w-0">
            <h1 className="mt-1 truncate text-xl font-semibold tracking-tight text-white">
              {asyncPatientName}
            </h1>
            <p className="mt-1 text-sm text-slate-300">
              {asyncModality || "Modalidade não informada"}
            </p>
            <p className="mt-1 text-xs text-slate-400">
              Segmentation targets: {asyncSegmentationTargets}
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <StatusPill status={currentAsyncStatus} />
            <Link href={`/studies/${asyncStatus.id}?async=1`}>
              <a className="inline-flex items-center gap-2 rounded-[8px] border border-white/10 bg-[#2a2c34] px-3 py-2 text-sm font-semibold text-slate-100 transition hover:bg-[#31343d]">
                <FolderOpen className="h-4 w-4" />
                Back to detail
              </a>
            </Link>
            <button
              type="button"
              onClick={() => void loadAsyncAssets()}
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

        {currentAsyncStatus !== "COMPLETED" ? (
          <Panel className="space-y-4">
            <p className="text-lg font-semibold text-white">
              Viewer will unlock when processing completes
            </p>
            <p className="text-sm leading-7 text-slate-300">
              Este job ainda não finalizou. Assim que chegar em `COMPLETED`, o
              viewer passa a carregar `ORIGINAL_NIFTI` e `MASK_NIFTI`.
            </p>
          </Panel>
        ) : asyncAssets?.imageUrl && asyncAssets?.maskUrl ? (
          <div className="-mx-4 md:-mx-6 lg:-mx-8">
            <OrthogonalViewer
              imageUrl={asyncAssets.imageUrl}
              maskUrl={asyncAssets.maskUrl}
              modality={asyncModality || null}
              segmentsLegend={asyncAssets.segmentsLegend}
              fallbackSegmentNames={asyncAssets.fallbackSegmentNames}
              descriptiveAnalysis={asyncAssets.descriptiveAnalysis}
            />
          </div>
        ) : (
          <Panel className="space-y-4">
            <p className="text-lg font-semibold text-white">
              Result assets not ready
            </p>
            <p className="text-sm leading-7 text-slate-300">
              O job está `COMPLETED`, mas o frontend não encontrou os dois
              artefatos necessários para o viewer (`ORIGINAL_NIFTI` e
              `MASK_NIFTI`).
            </p>
          </Panel>
        )}
      </motion.section>
    );
  }

  if (!study) {
    return (
      <InlineNotice title="Study unavailable" tone="danger">
        {error || "The study could not be loaded from the backend."}
      </InlineNotice>
    );
  }

  const currentStatus = statusSnapshot?.status || study.status;
  const legacySegmentationTargets = formatSegmentationTargets(
    result?.segments_legend?.map((segment) => segment.label) ||
      [study.category || ""],
  );

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
            {study.case_identification || study.patient_name || "Estudo clínico"}
          </h1>
          <p className="mt-1 text-sm text-slate-300">
            {study.exam_modality || "Unknown"}
          </p>
          <p className="mt-1 text-xs text-slate-400">
            Segmentation targets: {legacySegmentationTargets}
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
            descriptiveAnalysis={result.descriptive_analysis}
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

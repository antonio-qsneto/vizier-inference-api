import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "wouter";
import { motion } from "framer-motion";
import { ArrowUpFromLine, Eye, Search, SlidersHorizontal } from "lucide-react";
import {
  fetchInferenceJobsPage,
  fetchStudiesPage,
  getPageResults,
} from "@/api/services";
import { useAuth } from "@/auth/AuthContext";
import {
  EmptyState,
  InlineNotice,
  LoadingState,
  PageIntro,
  Panel,
  StatusPill,
} from "@/components/primitives";
import { env } from "@/env";
import { formatDateTime } from "@/lib/format";
import {
  DEMO_STUDY_CASE_TITLE,
  DEMO_STUDY_CATEGORY,
  DEMO_STUDY_CREATED_AT,
  DEMO_STUDY_ID,
  DEMO_STUDY_MODALITY,
  DEMO_STUDY_PATIENT_NAME,
  DEMO_STUDY_VIEWER_HREF,
} from "@/lib/demo-study";
import type { InferenceJobListItem, Study } from "@/types/api";

interface ClinicalCaseRow {
  id: string;
  caseIdentification: string;
  patientName: string;
  category: string;
  examModality: string;
  ownerEmail: string;
  status: string;
  createdAt: string;
  detailHref: string;
  isAsync: boolean;
}

const STATUS_FILTER_LABELS: Record<string, string> = {
  ALL: "Todos",
  SUBMITTED: "Enviado",
  PROCESSING: "Processando",
  COMPLETED: "Concluído",
  FAILED: "Falhou",
};

function mapAsyncStatusToCaseStatus(status: string) {
  const normalized = (status || "").toUpperCase();
  if (normalized === "COMPLETED") {
    return "COMPLETED";
  }
  if (normalized === "FAILED") {
    return "FAILED";
  }
  if (normalized === "CREATED" || normalized === "UPLOAD_PENDING" || normalized === "UPLOADED") {
    return "SUBMITTED";
  }
  return "PROCESSING";
}

export default function StudiesPage() {
  const { accessToken } = useAuth();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [studies, setStudies] = useState<Study[]>([]);
  const [inferenceJobs, setInferenceJobs] = useState<InferenceJobListItem[]>([]);
  const [statusFilter, setStatusFilter] = useState("ALL");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const [totalCount, setTotalCount] = useState(0);

  const loadStudies = useCallback(async () => {
    if (!accessToken) {
      return;
    }

    setLoading(true);
    try {
      if (env.useAsyncS3Upload) {
        const inferencePayload = await fetchInferenceJobsPage(accessToken, {
          page,
          pageSize,
        });
        setStudies([]);
        setInferenceJobs(getPageResults<InferenceJobListItem>(inferencePayload));
        setTotalCount(
          typeof inferencePayload?.count === "number"
            ? inferencePayload.count
            : getPageResults<InferenceJobListItem>(inferencePayload).length,
        );
      } else {
        const studiesPayload = await fetchStudiesPage(accessToken, {
          page,
          pageSize,
        });
        setInferenceJobs([]);
        setStudies(getPageResults<Study>(studiesPayload));
        setTotalCount(
          typeof studiesPayload?.count === "number"
            ? studiesPayload.count
            : getPageResults<Study>(studiesPayload).length,
        );
      }
      setError(null);
    } catch (requestError) {
      if (requestError instanceof Error) {
        setError(requestError.message);
      }
    } finally {
      setLoading(false);
    }
  }, [accessToken, page, pageSize]);

  useEffect(() => {
    void loadStudies();
  }, [loadStudies]);

  const caseRows = useMemo<ClinicalCaseRow[]>(() => {
    const demoRow: ClinicalCaseRow = {
      id: DEMO_STUDY_ID,
      caseIdentification: DEMO_STUDY_CASE_TITLE,
      patientName: DEMO_STUDY_PATIENT_NAME,
      category: DEMO_STUDY_CATEGORY,
      examModality: DEMO_STUDY_MODALITY,
      ownerEmail: "--",
      status: "COMPLETED",
      createdAt: DEMO_STUDY_CREATED_AT,
      detailHref: DEMO_STUDY_VIEWER_HREF,
      isAsync: false,
    };

    const legacyRows = studies.map<ClinicalCaseRow>((study) => ({
      id: study.id,
      caseIdentification:
        study.case_identification || study.patient_name || "Estudo sem identificação",
      patientName: study.patient_name || "Paciente sem nome",
      category: study.category || "--",
      examModality: study.exam_modality || "Desconhecida",
      ownerEmail: study.owner_email || "--",
      status: study.status || "SUBMITTED",
      createdAt: study.created_at,
      detailHref: `/studies/${study.id}/viewer`,
      isAsync: false,
    }));

    const asyncRows = inferenceJobs.map<ClinicalCaseRow>((job) => {
      const payload = (job.request_payload || {}) as Record<string, unknown>;
      const caseIdentification =
        String(payload.case_identification || "").trim() ||
        String(payload.patient_name || "").trim() ||
        "Inferência assíncrona";
      const patientName = String(payload.patient_name || "").trim() || "Paciente sem nome";
      const category = String(payload.category_id || "").trim() || "Inferência assíncrona";
      const examModality = String(payload.exam_modality || "").trim() || "Desconhecida";

      return {
        id: job.id,
        caseIdentification,
        patientName,
        category,
        examModality,
        ownerEmail: job.owner_email || "--",
        status: mapAsyncStatusToCaseStatus(job.status),
        createdAt: job.created_at,
        detailHref: `/studies/${job.id}/viewer?async=1`,
        isAsync: true,
      };
    });

    const sortedRows = [...asyncRows, ...legacyRows].sort((left, right) =>
      (right.createdAt || "").localeCompare(left.createdAt || ""),
    );
    return [...sortedRows, demoRow];
  }, [inferenceJobs, studies]);

  const visibleStudies = useMemo(() => {
    const query = search.trim().toLowerCase();
    return caseRows.filter((study) => {
      const matchesStatus =
        statusFilter === "ALL" ? true : study.status === statusFilter;
      const haystack = [
        study.caseIdentification,
        study.patientName,
        study.category,
        study.examModality,
        study.ownerEmail,
      ]
        .join(" ")
        .toLowerCase();
      const matchesQuery = query ? haystack.includes(query) : true;
      return matchesStatus && matchesQuery;
    });
  }, [caseRows, search, statusFilter]);

  const loadedRealCount = useMemo(
    () => caseRows.filter((study) => study.id !== DEMO_STUDY_ID).length,
    [caseRows],
  );
  const demoRowVisible = useMemo(
    () => visibleStudies.find((study) => study.id === DEMO_STUDY_ID) || null,
    [visibleStudies],
  );
  const visibleRealStudies = useMemo(
    () => visibleStudies.filter((study) => study.id !== DEMO_STUDY_ID),
    [visibleStudies],
  );

  const shouldApplyClientPaginationFallback =
    loadedRealCount > pageSize && totalCount <= loadedRealCount;
  const effectiveTotalCount = shouldApplyClientPaginationFallback
    ? visibleStudies.length
    : totalCount + (demoRowVisible ? 1 : 0);
  const totalPages = Math.max(1, Math.ceil(effectiveTotalCount / pageSize));
  const displayedStudies = shouldApplyClientPaginationFallback
    ? visibleStudies.slice((page - 1) * pageSize, page * pageSize)
    : (() => {
        if (!demoRowVisible || page !== totalPages) {
          return visibleRealStudies;
        }
        if (visibleRealStudies.length >= pageSize) {
          return visibleRealStudies;
        }
        return [...visibleRealStudies, demoRowVisible];
      })();

  useEffect(() => {
    if (page > totalPages) {
      setPage(totalPages);
    }
  }, [page, totalPages]);

  if (loading) {
    return <LoadingState label="Carregando estudos..." />;
  }

  return (
    <motion.section
      initial={{ opacity: 0, y: 18 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35 }}
      className="space-y-6"
    >
      <PageIntro
        eyebrow="Casos clínicos"
        title="Casos clínicos"
        description="Gerencie e revise todos os estudos enviados para a plataforma."
        actions={
          <Link href="/studies/new">
            <a className="inline-flex items-center gap-2 rounded-[10px] border border-sky-300/25 bg-sky-500/14 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-sky-500/20">
              <ArrowUpFromLine className="h-4 w-4" />
              Novo estudo
            </a>
          </Link>
        }
      />

      {error ? (
        <InlineNotice title="Falha ao carregar estudos">{error}</InlineNotice>
      ) : null}

      <Panel className="space-y-4">
        <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_240px_180px]">
          <label className="flex items-center gap-3 rounded-[12px] border border-white/8 bg-[#25262d] px-4 py-3">
            <Search className="h-4 w-4 text-sky-400" />
            <input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Buscar por paciente, caso, categoria ou responsável"
              className="w-full bg-transparent text-sm text-white outline-none placeholder:text-slate-500"
            />
          </label>
          <label className="flex items-center gap-3 rounded-[12px] border border-white/8 bg-[#25262d] px-4 py-3">
            <SlidersHorizontal className="h-4 w-4 text-sky-400" />
            <select
              value={statusFilter}
              onChange={(event) => setStatusFilter(event.target.value)}
              className="w-full bg-transparent text-sm text-white outline-none"
            >
              {["ALL", "SUBMITTED", "PROCESSING", "COMPLETED", "FAILED"].map(
                (status) => (
                  <option key={status} value={status} className="bg-slate-900">
                    {STATUS_FILTER_LABELS[status] || status}
                  </option>
                ),
              )}
            </select>
          </label>
          <label className="flex items-center gap-3 rounded-[12px] border border-white/8 bg-[#25262d] px-4 py-3">
            <span className="text-xs font-semibold uppercase tracking-[0.12em] text-slate-400">
              Itens
            </span>
            <select
              value={String(pageSize)}
              onChange={(event) => {
                const next = Number(event.target.value);
                setPageSize(next);
                setPage(1);
              }}
              className="w-full bg-transparent text-sm text-white outline-none"
            >
              {[10, 50, 100].map((size) => (
                <option key={size} value={size} className="bg-slate-900">
                  {size}
                </option>
              ))}
            </select>
          </label>
        </div>
        <div className="flex items-center justify-between gap-3 text-sm text-slate-300">
          <p>
            Página {page} de {totalPages} · {effectiveTotalCount} estudos
          </p>
          <div className="flex items-center gap-2">
            <button
              type="button"
              disabled={page <= 1}
              onClick={() => setPage((current) => Math.max(1, current - 1))}
              className="rounded-lg border border-white/12 bg-white/6 px-3 py-1.5 text-xs font-semibold text-slate-100 transition hover:bg-white/10 disabled:cursor-not-allowed disabled:opacity-40"
            >
              Anterior
            </button>
            <button
              type="button"
              disabled={page >= totalPages}
              onClick={() =>
                setPage((current) => Math.min(totalPages, current + 1))
              }
              className="rounded-lg border border-white/12 bg-white/6 px-3 py-1.5 text-xs font-semibold text-slate-100 transition hover:bg-white/10 disabled:cursor-not-allowed disabled:opacity-40"
            >
              Próxima
            </button>
          </div>
        </div>
      </Panel>

      {displayedStudies.length ? (
        <Panel className="overflow-hidden p-0">
          <div className="overflow-x-auto">
            <div className="min-w-[980px]">
              <div className="grid grid-cols-[1.1fr_1fr_0.7fr_0.9fr_0.9fr_0.65fr] gap-4 border-b border-white/6 px-6 py-4 text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">
                <span>Caso</span>
                <span>Paciente</span>
                <span>Modalidade</span>
                <span>Responsável</span>
                <span>Status</span>
                <span>Ação</span>
              </div>

              <div className="divide-y divide-white/6">
                {displayedStudies.map((study) => (
                  <div
                    key={study.id}
                    className="grid grid-cols-[1.1fr_1fr_0.7fr_0.9fr_0.9fr_0.65fr] gap-4 px-6 py-4 transition hover:bg-white/4"
                  >
                    <div className="space-y-1">
                      <p className="font-medium text-white">
                        {study.caseIdentification}
                      </p>
                      <p className="text-sm text-slate-500">
                        {formatDateTime(study.createdAt)}
                      </p>
                    </div>

                    <div className="space-y-1">
                      <p className="font-medium text-slate-100">
                        {study.patientName}
                      </p>
                      <p className="text-sm text-slate-500">{study.category}</p>
                    </div>

                    <div className="flex items-center text-slate-300">
                      {study.examModality || "Desconhecida"}
                    </div>

                    <div className="flex items-center text-sm text-slate-400">
                      {study.ownerEmail || "--"}
                    </div>

                    <div className="flex items-center">
                      <StatusPill status={study.status} />
                    </div>

                    <div className="flex items-center">
                      <Link href={study.detailHref}>
                        <a className="inline-flex items-center gap-2 text-sm font-semibold text-sky-400 transition hover:text-sky-300">
                          <Eye className="h-4 w-4" />
                          Ver
                        </a>
                      </Link>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </Panel>
      ) : (
        <EmptyState
          title="Nenhum estudo encontrado"
          description="Nenhum estudo corresponde aos filtros atuais. Use `Novo estudo` para enviar um volume compatível com o backend."
        />
      )}
    </motion.section>
  );
}

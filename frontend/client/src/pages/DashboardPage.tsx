import { useCallback, useEffect, useState } from "react";
import { Link } from "wouter";
import { motion } from "framer-motion";
import {
  CheckCircle2,
  Clock3,
  Eye,
  HeartPulse,
  TriangleAlert,
  UserRound,
} from "lucide-react";
import {
  fetchHealth,
  fetchInferenceJobs,
  fetchStudies,
  getPageResults,
} from "@/api/services";
import { useAuth } from "@/auth/AuthContext";
import {
  InlineNotice,
  LoadingState,
  MetricCard,
  PageIntro,
  Panel,
  StatusPill,
} from "@/components/primitives";
import { formatDateTime } from "@/lib/format";
import { env } from "@/env";
import type {
  HealthStatus,
  InferenceJobListItem,
  Study,
} from "@/types/api";

interface RecentCaseRow {
  id: string;
  title: string;
  patient: string;
  category: string;
  modality: string;
  status: string;
  createdAt: string;
  href: string;
}

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

export default function DashboardPage() {
  const { accessToken, user } = useAuth();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [health, setHealth] = useState<HealthStatus | null>(null);
  const [studies, setStudies] = useState<Study[]>([]);
  const [inferenceJobs, setInferenceJobs] = useState<InferenceJobListItem[]>([]);

  const loadDashboard = useCallback(async () => {
    if (!accessToken) {
      return;
    }

    setLoading(true);
    try {
      const [healthResponse, studiesResponse, inferenceResponse] =
        await Promise.allSettled([
        fetchHealth(),
        fetchStudies(accessToken),
        env.useAsyncS3Upload ? fetchInferenceJobs(accessToken) : Promise.resolve(null),
      ]);

      setHealth(healthResponse.status === "fulfilled" ? healthResponse.value : null);
      setStudies(
        studiesResponse.status === "fulfilled"
          ? getPageResults<Study>(studiesResponse.value)
          : [],
      );
      setInferenceJobs(
        inferenceResponse.status === "fulfilled" &&
          inferenceResponse.value &&
          typeof inferenceResponse.value === "object" &&
          Array.isArray((inferenceResponse.value as { results?: unknown }).results)
          ? ((inferenceResponse.value as { results: InferenceJobListItem[] }).results || [])
          : [],
      );

      const failures = [healthResponse, studiesResponse, inferenceResponse]
        .filter((result) => result.status === "rejected")
        .map((result) => {
          const reason = (result as PromiseRejectedResult).reason;
          return reason instanceof Error ? reason.message : "Falha ao carregar painel";
        });

      setError(failures.length ? failures[0] : null);
    } catch (requestError) {
      if (requestError instanceof Error) {
        setError(requestError.message);
      }
    } finally {
      setLoading(false);
    }
  }, [accessToken]);

  useEffect(() => {
    void loadDashboard();
  }, [loadDashboard]);

  if (loading) {
    return <LoadingState label="Montando painel clínico..." />;
  }

  const completedStudies = studies.filter(
    (study) => study.status === "COMPLETED",
  );
  const failedStudies = studies.filter((study) => study.status === "FAILED");
  const processingStudies = studies.filter(
    (study) => study.status === "PROCESSING" || study.status === "SUBMITTED",
  );
  const recentCases: RecentCaseRow[] = [
    ...inferenceJobs.map((job) => {
      const payload = (job.request_payload || {}) as Record<string, unknown>;
      const caseIdentification = String(payload.case_identification || "").trim();
      const patientName = String(payload.patient_name || "").trim();
      const category = String(payload.category_id || "").trim();
      const modality = String(payload.exam_modality || "").trim();
      return {
        id: job.id,
        title: caseIdentification || patientName || "Estudo assíncrono",
        patient: patientName || "Paciente sem nome",
        category: category || "Inferência assíncrona",
        modality: modality || "Desconhecida",
        status: mapAsyncStatusToCaseStatus(job.status),
        createdAt: job.created_at,
        href: `/studies/${job.id}/viewer?async=1`,
      };
    }),
    ...studies.map((study) => ({
      id: study.id,
      title: study.case_identification || study.patient_name || "Estudo sem identificação",
      patient: study.patient_name || "Paciente sem nome",
      category: study.category || "--",
      modality: study.exam_modality || "Desconhecida",
      status: study.status || "SUBMITTED",
      createdAt: study.created_at,
      href: `/studies/${study.id}/viewer`,
    })),
  ]
    .sort((left, right) => (right.createdAt || "").localeCompare(left.createdAt || ""))
    .slice(0, 5);

  return (
    <motion.section
      initial={{ opacity: 0, y: 18 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35 }}
      className="space-y-6"
    >
      <PageIntro
        eyebrow="Painel"
        title="Painel"
        description="Visão geral dos casos clínicos, status do backend e do seu espaço de trabalho."
      />

      {error ? (
        <InlineNotice title="Falha ao carregar o painel">{error}</InlineNotice>
      ) : null}

      <div className="grid gap-4 xl:grid-cols-4">
        <MetricCard
          label="Exames em processamento"
          value={String(processingStudies.length)}
          detail="Estudos em fila, enviados ou com inferência ativa."
          icon={Clock3}
          tone="amber"
        />
        <MetricCard
          label="Achados críticos"
          value={String(failedStudies.length)}
          detail="Estudos com falha ou bloqueados, exigindo revisão do operador."
          icon={TriangleAlert}
          tone="rose"
        />
        <MetricCard
          label="Análises concluídas"
          value={String(completedStudies.length)}
          detail={`${studies.length} estudos totais registrados no espaço de trabalho.`}
          icon={CheckCircle2}
          tone="emerald"
        />
        <MetricCard
          label="Status do sistema"
          value={
            health?.status === "ok" ? "Saudável" : health?.status || "Desconhecido"
          }
          detail={
            health?.version
              ? `Versão do backend ${health.version}`
              : "Nenhuma versão reportada"
          }
          icon={HeartPulse}
          tone="blue"
        />
      </div>

      <div className="space-y-6">
        <Panel className="space-y-5">
          <div className="flex items-center justify-between gap-4">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">
                Casos recentes
              </p>
              <h2 className="mt-2 text-2xl font-semibold text-white">
                Atividade clínica
              </h2>
            </div>
            <Link href="/studies">
              <a className="inline-flex items-center gap-2 rounded-[10px] border border-white/8 bg-[#25262d] px-4 py-2 text-sm font-semibold text-slate-100 transition hover:bg-[#2e3038]">
                <Eye className="h-4 w-4 text-sky-400" />
                Abrir estudos
              </a>
            </Link>
          </div>

          <div className="overflow-hidden rounded-[14px] border border-white/8 bg-[#2b2c33]">
            <div className="overflow-x-auto">
              <div className="min-w-[720px]">
                <div className="grid grid-cols-[1.3fr_1fr_0.8fr_0.9fr] gap-4 border-b border-white/6 px-6 py-4 text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">
                  <span>Caso</span>
                  <span>Paciente</span>
                  <span>Modalidade</span>
                  <span>Status</span>
                </div>

                <div className="divide-y divide-white/6">
                  {recentCases.length ? (
                    recentCases.map((study) => (
                    <Link key={study.id} href={study.href}>
                      <a className="grid grid-cols-[1.3fr_1fr_0.8fr_0.9fr] gap-4 px-6 py-4 transition hover:bg-white/4">
                        <div className="space-y-1">
                          <p className="font-medium text-white">
                            {study.title}
                          </p>
                          <p className="text-sm text-slate-500">
                            {formatDateTime(study.createdAt)}
                          </p>
                        </div>
                        <div className="space-y-1">
                          <p className="font-medium text-slate-100">
                            {study.patient}
                          </p>
                          <p className="text-sm text-slate-500">
                            {study.category}
                          </p>
                        </div>
                        <div className="flex items-center text-slate-300">
                          {study.modality}
                        </div>
                        <div className="flex items-center">
                          <StatusPill status={study.status || "SUBMITTED"} />
                        </div>
                      </a>
                    </Link>
                  ))
                  ) : (
                    <div className="px-6 py-8 text-sm text-slate-400">
                      Nenhum estudo disponível ainda.
                    </div>
                  )}
                </div>
              </div>
            </div>
          </div>
        </Panel>
        <Panel className="space-y-4">
          <div className="flex items-start justify-between gap-4">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">
                Conta
              </p>
              <h2 className="mt-2 text-2xl font-semibold text-white">
                {user?.full_name || "Usuário autenticado"}
              </h2>
            </div>
            <div className="inline-flex h-12 w-12 items-center justify-center rounded-[14px] border border-sky-400/20 bg-sky-500/12 text-sky-300">
              <UserRound className="h-5 w-5" />
            </div>
          </div>
          <div className="space-y-3 text-sm text-slate-400">
            <div className="flex items-center justify-between rounded-[12px] border border-white/8 bg-[#25262d] px-4 py-3">
              <span>Email</span>
              <span className="font-medium text-slate-200">
                {user?.email || "--"}
              </span>
            </div>
            <div className="flex items-center justify-between rounded-[12px] border border-white/8 bg-[#25262d] px-4 py-3">
              <span>Plano</span>
              <span className="font-medium text-slate-200">
                {user?.subscription_plan || "gratuito"}
              </span>
            </div>
          </div>
        </Panel>
      </div>
    </motion.section>
  );
}

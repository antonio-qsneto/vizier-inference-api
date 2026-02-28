import { useCallback, useEffect, useState } from "react";
import { Link } from "wouter";
import { motion } from "framer-motion";
import {
  Building2,
  CheckCircle2,
  Clock3,
  Eye,
  HeartPulse,
  TriangleAlert,
  UserRound,
} from "lucide-react";
import {
  fetchClinics,
  fetchHealth,
  fetchMyInvitations,
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
import type {
  Clinic,
  DoctorInvitation,
  HealthStatus,
  Study,
} from "@/types/api";

export default function DashboardPage() {
  const { accessToken, user } = useAuth();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [health, setHealth] = useState<HealthStatus | null>(null);
  const [clinic, setClinic] = useState<Clinic | null>(null);
  const [studies, setStudies] = useState<Study[]>([]);
  const [invitations, setInvitations] = useState<DoctorInvitation[]>([]);

  const loadDashboard = useCallback(async () => {
    if (!accessToken) {
      return;
    }

    setLoading(true);
    try {
      const [
        healthResponse,
        clinicsResponse,
        studiesResponse,
        invitationsResponse,
      ] = await Promise.all([
        fetchHealth(),
        fetchClinics(accessToken),
        fetchStudies(accessToken),
        fetchMyInvitations(accessToken),
      ]);

      setHealth(healthResponse);
      setClinic(getPageResults(clinicsResponse)[0] ?? null);
      setStudies(getPageResults(studiesResponse));
      setInvitations(invitationsResponse);
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

  return (
    <motion.section
      initial={{ opacity: 0, y: 18 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35 }}
      className="space-y-6"
    >
      <PageIntro
        eyebrow="Dashboard"
        title="Dashboard"
        description="Overview of clinical cases, backend status and your active workspace."
      />

      {error ? (
        <InlineNotice title="Dashboard request failed">{error}</InlineNotice>
      ) : null}

      <div className="grid gap-4 xl:grid-cols-4">
        <MetricCard
          label="Exams in processing"
          value={String(processingStudies.length)}
          detail="Studies in queue, submission or active inference."
          icon={Clock3}
          tone="amber"
        />
        <MetricCard
          label="Critical findings"
          value={String(failedStudies.length)}
          detail="Failed or blocked studies requiring operator review."
          icon={TriangleAlert}
          tone="rose"
        />
        <MetricCard
          label="Completed analyses"
          value={String(completedStudies.length)}
          detail={`${studies.length} total studies registered in the workspace.`}
          icon={CheckCircle2}
          tone="emerald"
        />
        <MetricCard
          label="System status"
          value={
            health?.status === "ok" ? "Healthy" : health?.status || "Unknown"
          }
          detail={
            health?.version
              ? `Backend version ${health.version}`
              : "No version reported"
          }
          icon={HeartPulse}
          tone="blue"
        />
      </div>

      <div className="grid gap-6 xl:grid-cols-[1.25fr_0.75fr]">
        <Panel className="space-y-5">
          <div className="flex items-center justify-between gap-4">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">
                Recent cases
              </p>
              <h2 className="mt-2 text-2xl font-semibold text-white">
                Clinical activity
              </h2>
            </div>
            <Link href="/studies">
              <a className="inline-flex items-center gap-2 rounded-[10px] border border-white/8 bg-[#25262d] px-4 py-2 text-sm font-semibold text-slate-100 transition hover:bg-[#2e3038]">
                <Eye className="h-4 w-4 text-sky-400" />
                Open studies
              </a>
            </Link>
          </div>

          <div className="overflow-hidden rounded-[14px] border border-white/8 bg-[#2b2c33]">
            <div className="overflow-x-auto">
              <div className="min-w-[720px]">
                <div className="grid grid-cols-[1.3fr_1fr_0.8fr_0.9fr] gap-4 border-b border-white/6 px-6 py-4 text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">
                  <span>Case</span>
                  <span>Patient</span>
                  <span>Modality</span>
                  <span>Status</span>
                </div>

                <div className="divide-y divide-white/6">
                  {studies.slice(0, 5).map((study) => (
                    <Link key={study.id} href={`/studies/${study.id}`}>
                      <a className="grid grid-cols-[1.3fr_1fr_0.8fr_0.9fr] gap-4 px-6 py-4 transition hover:bg-white/4">
                        <div className="space-y-1">
                          <p className="font-medium text-white">
                            {study.case_identification || study.id}
                          </p>
                          <p className="text-sm text-slate-500">
                            {formatDateTime(study.created_at)}
                          </p>
                        </div>
                        <div className="space-y-1">
                          <p className="font-medium text-slate-100">
                            {study.patient_name || "Unnamed patient"}
                          </p>
                          <p className="text-sm text-slate-500">
                            {study.category}
                          </p>
                        </div>
                        <div className="flex items-center text-slate-300">
                          {study.exam_modality || "Unknown"}
                        </div>
                        <div className="flex items-center">
                          <StatusPill status={study.status} />
                        </div>
                      </a>
                    </Link>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </Panel>

        <div className="space-y-6">
          <Panel className="space-y-4">
            <div className="flex items-start justify-between gap-4">
              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">
                  Workspace
                </p>
                <h2 className="mt-2 text-2xl font-semibold text-white">
                  {clinic?.name || user?.clinic_name || "Individual workspace"}
                </h2>
              </div>
              <div className="inline-flex h-12 w-12 items-center justify-center rounded-[14px] border border-sky-400/20 bg-sky-500/12 text-sky-300">
                <Building2 className="h-5 w-5" />
              </div>
            </div>
            <div className="space-y-3 text-sm text-slate-400">
              <p>
                {clinic
                  ? `${clinic.active_doctors_count} active doctors and seat limit ${clinic.seat_limit}.`
                  : "No clinic linked yet. You can complete onboarding from the Clinic page."}
              </p>
              <div className="flex items-center justify-between rounded-[12px] border border-white/8 bg-[#25262d] px-4 py-3">
                <span>Pending invitations</span>
                <span className="font-semibold text-white">
                  {invitations.length}
                </span>
              </div>
            </div>
          </Panel>

          <Panel className="space-y-4">
            <div className="flex items-start justify-between gap-4">
              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">
                  Account
                </p>
                <h2 className="mt-2 text-2xl font-semibold text-white">
                  {user?.full_name || "Authenticated user"}
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
                <span>Plan</span>
                <span className="font-medium text-slate-200">
                  {user?.subscription_plan || "free"}
                </span>
              </div>
            </div>
          </Panel>
        </div>
      </div>
    </motion.section>
  );
}

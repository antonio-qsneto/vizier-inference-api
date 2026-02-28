import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "wouter";
import { motion } from "framer-motion";
import { ArrowUpFromLine, Eye, Search, SlidersHorizontal } from "lucide-react";
import { fetchStudies, getPageResults } from "@/api/services";
import { useAuth } from "@/auth/AuthContext";
import {
  EmptyState,
  InlineNotice,
  LoadingState,
  PageIntro,
  Panel,
  StatusPill,
} from "@/components/primitives";
import { formatDateTime } from "@/lib/format";
import type { Study } from "@/types/api";

export default function StudiesPage() {
  const { accessToken } = useAuth();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [studies, setStudies] = useState<Study[]>([]);
  const [statusFilter, setStatusFilter] = useState("ALL");
  const [search, setSearch] = useState("");

  const loadStudies = useCallback(async () => {
    if (!accessToken) {
      return;
    }

    setLoading(true);
    try {
      const payload = await fetchStudies(accessToken);
      setStudies(getPageResults(payload));
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
    void loadStudies();
  }, [loadStudies]);

  const visibleStudies = useMemo(() => {
    const query = search.trim().toLowerCase();
    return studies.filter((study) => {
      const matchesStatus =
        statusFilter === "ALL" ? true : study.status === statusFilter;
      const haystack = [
        study.case_identification,
        study.patient_name,
        study.category,
        study.exam_modality,
        study.owner_email,
      ]
        .join(" ")
        .toLowerCase();
      const matchesQuery = query ? haystack.includes(query) : true;
      return matchesStatus && matchesQuery;
    });
  }, [search, statusFilter, studies]);

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
        eyebrow="Clinical Cases"
        title="Clinical Cases"
        description="Manage and review all studies submitted to the platform."
        actions={
          <Link href="/studies/new">
            <a className="inline-flex items-center gap-2 rounded-[10px] border border-sky-300/25 bg-sky-500/14 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-sky-500/20">
              <ArrowUpFromLine className="h-4 w-4" />
              New study
            </a>
          </Link>
        }
      />

      {error ? (
        <InlineNotice title="Studies request failed">{error}</InlineNotice>
      ) : null}

      <Panel className="space-y-4">
        <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_240px]">
          <label className="flex items-center gap-3 rounded-[12px] border border-white/8 bg-[#25262d] px-4 py-3">
            <Search className="h-4 w-4 text-sky-400" />
            <input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Search by patient, case, category or owner"
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
                    {status}
                  </option>
                ),
              )}
            </select>
          </label>
        </div>
      </Panel>

      {visibleStudies.length ? (
        <Panel className="overflow-hidden p-0">
          <div className="overflow-x-auto">
            <div className="min-w-[980px]">
              <div className="grid grid-cols-[1.1fr_1fr_0.7fr_0.9fr_0.9fr_0.65fr] gap-4 border-b border-white/6 px-6 py-4 text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">
                <span>Case ID</span>
                <span>Patient</span>
                <span>Modality</span>
                <span>Owner</span>
                <span>Status</span>
                <span>Action</span>
              </div>

              <div className="divide-y divide-white/6">
                {visibleStudies.map((study) => (
                  <div
                    key={study.id}
                    className="grid grid-cols-[1.1fr_1fr_0.7fr_0.9fr_0.9fr_0.65fr] gap-4 px-6 py-4 transition hover:bg-white/4"
                  >
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
                      <p className="text-sm text-slate-500">{study.category}</p>
                    </div>

                    <div className="flex items-center text-slate-300">
                      {study.exam_modality || "Unknown"}
                    </div>

                    <div className="flex items-center text-sm text-slate-400">
                      {study.owner_email || "--"}
                    </div>

                    <div className="flex items-center">
                      <StatusPill status={study.status} />
                    </div>

                    <div className="flex items-center">
                      <Link href={`/studies/${study.id}`}>
                        <a className="inline-flex items-center gap-2 text-sm font-semibold text-sky-400 transition hover:text-sky-300">
                          <Eye className="h-4 w-4" />
                          View
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
          title="No studies found"
          description="Nenhum estudo corresponde aos filtros atuais. Use `New study` para enviar um volume compatível com o backend."
        />
      )}
    </motion.section>
  );
}

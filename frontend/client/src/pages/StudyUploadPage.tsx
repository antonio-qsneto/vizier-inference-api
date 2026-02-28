import { FormEvent, useCallback, useEffect, useState } from "react";
import { useLocation } from "wouter";
import { motion } from "framer-motion";
import { toast } from "sonner";
import { fetchCategories, uploadStudy } from "@/api/services";
import { useAuth } from "@/auth/AuthContext";
import { InlineNotice, LoadingState, PageIntro, Panel } from "@/components/primitives";
import type { CategoriesCatalog } from "@/types/api";

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

export default function StudyUploadPage() {
  const [, navigate] = useLocation();
  const { accessToken } = useAuth();
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

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!accessToken || !formState.file) {
      toast.error("Select a supported file before submitting");
      return;
    }

    const ageValue = Number(formState.age);
    if (!Number.isFinite(ageValue) || ageValue < 0) {
      toast.error("Age must be a valid positive number");
      return;
    }

    setSubmitting(true);
    try {
      const study = await uploadStudy(accessToken, {
        file: formState.file,
        caseIdentification: formState.caseIdentification.trim(),
        patientName: formState.patientName.trim(),
        age: ageValue,
        examSource: formState.examSource.trim(),
        examModality: formState.examModality,
        categoryId: formState.categoryId,
      });
      toast.success("Study submitted");
      navigate(`/studies/${study.id}`);
    } catch (requestError) {
      toast.error(requestError instanceof Error ? requestError.message : "Study upload failed");
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
        eyebrow="Upload"
        title="Submit a study to the inference pipeline"
        description="O payload segue exatamente o serializer do backend: arquivo + `case_identification`, `patient_name`, `age`, `exam_source`, `exam_modality` e `category_id`."
      />

      {error ? <InlineNotice title="Catalog load failed">{error}</InlineNotice> : null}

      <form onSubmit={handleSubmit} className="grid gap-6 xl:grid-cols-[1.1fr_0.9fr]">
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
              placeholder="Patient name"
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
              placeholder="Age"
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
              placeholder="Exam source"
              className="rounded-2xl border border-white/10 bg-white/6 px-4 py-3 text-sm text-white outline-none placeholder:text-slate-500 focus:border-sky-300/50"
            />
          </div>

          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <label className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-400">
                Exam Modality
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
                  Select modality
                </option>
                {modalities.map((modality) => (
                  <option key={modality} value={modality} className="bg-slate-900">
                    {modality}
                  </option>
                ))}
              </select>
            </div>
            <div className="space-y-2">
              <label className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-400">
                Target Group
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
                  Select group
                </option>
                {targetGroups.map((group) => (
                  <option key={group} value={group} className="bg-slate-900">
                    {group}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <label className="block rounded-[28px] border border-dashed border-white/15 bg-white/5 p-6">
            <span className="text-sm font-semibold text-white">
              Upload ZIP, NPZ, NIfTI (.nii / .nii.gz)
            </span>
            <p className="mt-2 text-sm leading-7 text-slate-300">
              O serializer atual não aceita `.dcm` isolado. Para DICOM, compacte
              a série em `.zip`.
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
          </label>

          <button
            type="submit"
            disabled={submitting}
            className="rounded-2xl bg-sky-500 px-5 py-3 text-sm font-semibold text-white transition hover:bg-sky-400 disabled:cursor-not-allowed disabled:opacity-60"
          >
            Submit study
          </button>
        </Panel>

        <div className="space-y-6">
          <Panel className="space-y-4">
            <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-400">
              Payload preview
            </p>
            <div className="space-y-2 rounded-3xl border border-white/10 bg-white/5 p-4 font-mono text-sm text-slate-200">
              <p>exam_modality = {formState.examModality || "..."}</p>
              <p>category_id = {formState.categoryId || "..."}</p>
            </div>
            <p className="text-sm leading-7 text-slate-300">
              O frontend envia o grupo selecionado, não um alvo individual.
            </p>
          </Panel>

          <Panel className="space-y-4">
            <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-400">
              Included segmentation targets
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
                Selecione modalidade e target group para visualizar os targets
                expandidos pelo backend.
              </p>
            )}
          </Panel>
        </div>
      </form>
    </motion.section>
  );
}

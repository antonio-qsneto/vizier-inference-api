import { startTransition, useEffect, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { ArrowRight, LogIn } from "lucide-react";
import { useLocation } from "wouter";
import { submitConsultationRequest } from "@/api/services";
import { useAuth } from "@/auth/AuthContext";
import DataFlowVisualization from "@/components/site/DataFlowVisualization";
import { COUNTRY_OPTIONS } from "@/lib/countries";
import type { ConsultationRequestPayload } from "@/types/api";

const VIDEO_SHOWCASE = [
  {
    title: "Triagem cerebral",
    subtitle: "CT/MRI para apoio ao diagnóstico de tumores e lesões.",
    src: "/site/videos/cerebro.mp4",
  },
  {
    title: "Análise hepática",
    subtitle: "Mapeamento de estruturas suspeitas em fígado e abdômen.",
    src: "/site/videos/figado.mp4",
  },
  {
    title: "Detecção pancreática",
    subtitle: "Segmentação e priorização de achados em exames complexos.",
    src: "/site/videos/pancreas.mp4",
  },
  {
    title: "Estruturas renais",
    subtitle: "Rastreamento de alterações focais em estudos volumétricos.",
    src: "/site/videos/rim.mp4",
  },
  {
    title: "Cólon e abdômen",
    subtitle: "Sinais iniciais para tomada de decisão clínica orientada.",
    src: "/site/videos/colon.mp4",
  },
] as const;

const HERO_ROTATION_MS = 4600;
const INITIAL_CONSULTATION_FORM: ConsultationRequestPayload = {
  first_name: "",
  last_name: "",
  company_name: "",
  job_title: "",
  email: "",
  country: "",
  message: "",
  discovery_source: "",
};

const IMPACT_HIGHLIGHTS = [
  {
    metric: "~27%",
    title: "Leitura radiológica mais ágil com IA assistiva",
    text: "Estudos indicam redução média de cerca de 27% no tempo de leitura quando a IA atua lado a lado com radiologistas.",
  },
  {
    metric: "35%+",
    title: "Diagnóstico acelerado do início ao laudo",
    text: "Em cenários clínicos reportados, o tempo médio de diagnóstico caiu de 8,2h para 5,3h, elevando a velocidade de resposta para casos críticos.",
  },
] as const;

export default function HomePage() {
  const [, navigate] = useLocation();
  const { status, signIn, isCognitoConfigured } = useAuth();
  const [activeVideoIndex, setActiveVideoIndex] = useState(0);
  const [consultationForm, setConsultationForm] = useState<ConsultationRequestPayload>(
    INITIAL_CONSULTATION_FORM,
  );
  const [submittingConsultation, setSubmittingConsultation] = useState(false);
  const [consultationSuccess, setConsultationSuccess] = useState<string | null>(null);
  const [consultationError, setConsultationError] = useState<string | null>(null);

  const isLogged = status === "authenticated";
  const isLoadingAuth = status === "loading";
  const activeVideo = VIDEO_SHOWCASE[activeVideoIndex];

  useEffect(() => {
    const intervalId = window.setInterval(() => {
      startTransition(() => {
        setActiveVideoIndex((current) => (current + 1) % VIDEO_SHOWCASE.length);
      });
    }, HERO_ROTATION_MS);

    return () => window.clearInterval(intervalId);
  }, []);

  function updateConsultationField(
    field: keyof ConsultationRequestPayload,
    value: string,
  ) {
    setConsultationForm((current) => ({
      ...current,
      [field]: value,
    }));
  }

  async function handleConsultationSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setConsultationError(null);
    setConsultationSuccess(null);
    setSubmittingConsultation(true);

    try {
      const payload: ConsultationRequestPayload = {
        first_name: consultationForm.first_name || "",
        last_name: consultationForm.last_name || "",
        company_name: consultationForm.company_name || "",
        job_title: consultationForm.job_title || "",
        email: consultationForm.email.trim(),
        country: consultationForm.country.trim(),
        message: consultationForm.message || "",
        discovery_source: consultationForm.discovery_source || "",
      };

      const response = await submitConsultationRequest(payload);
      setConsultationSuccess(response.detail);
      setConsultationForm(INITIAL_CONSULTATION_FORM);
    } catch (error) {
      if (error instanceof Error) {
        setConsultationError(error.message);
      } else {
        setConsultationError("Não foi possível enviar sua solicitação.");
      }
    } finally {
      setSubmittingConsultation(false);
    }
  }

  return (
    <div className="min-h-screen bg-[radial-gradient(circle_at_top_right,rgba(14,165,233,0.18),transparent_26%),radial-gradient(circle_at_top_left,rgba(8,145,178,0.22),transparent_28%),linear-gradient(180deg,#04070d,#060b14_32%,#08111a)] text-white">
      <header className="sticky top-0 z-20 border-b border-white/8 bg-slate-950/70 backdrop-blur-xl">
        <div className="mx-auto flex w-full max-w-7xl items-center justify-between px-4 py-3 md:px-8">
          <a href="/" className="inline-flex items-center gap-3">
            <img
              src="/site/vizier_white.svg"
              alt="Vizier"
              className="h-7 w-auto md:h-8"
              loading="eager"
            />
          </a>

          <div className="flex items-center gap-2 md:gap-3">
            {isLoadingAuth ? (
              <span className="rounded-full border border-white/15 px-4 py-2 text-xs text-slate-300 md:text-sm">
                Verificando sessão...
              </span>
            ) : null}

            {isLogged ? (
              <button
                type="button"
                onClick={() => navigate("/dashboard")}
                className="inline-flex items-center gap-2 rounded-full bg-cyan-500 px-4 py-2 text-xs font-semibold text-slate-950 transition hover:bg-cyan-400 md:text-sm"
              >
                Acessar painel
                <ArrowRight className="h-4 w-4" />
              </button>
            ) : (
              <>
                {isCognitoConfigured ? (
                  <>
                    <button
                      type="button"
                      onClick={() => void signIn("login")}
                      className="inline-flex items-center gap-2 rounded-full bg-cyan-500 px-4 py-2 text-xs font-semibold text-slate-950 transition hover:bg-cyan-400 md:text-sm"
                    >
                      <LogIn className="h-4 w-4" />
                      Login
                    </button>
                    <button
                      type="button"
                      onClick={() => void signIn("signup")}
                      className="rounded-full border border-white/20 bg-white/5 px-4 py-2 text-xs font-semibold text-slate-100 transition hover:bg-white/10 md:text-sm"
                    >
                      Criar conta
                    </button>
                  </>
                ) : (
                  <button
                    type="button"
                    onClick={() => void signIn("login")}
                    className="inline-flex items-center gap-2 rounded-full bg-cyan-500 px-4 py-2 text-xs font-semibold text-slate-950 transition hover:bg-cyan-400 md:text-sm"
                  >
                    <LogIn className="h-4 w-4" />
                    Login
                  </button>
                )}
              </>
            )}
          </div>
        </div>
      </header>

      <main className="mx-auto w-full max-w-7xl px-4 pb-14 pt-10 md:px-8 md:pt-14">
        <motion.section
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5 }}
          className="relative overflow-hidden rounded-[34px] border border-white/10"
        >
          <div className="relative h-[430px] bg-slate-900 md:h-[500px]">
            <AnimatePresence mode="wait">
              <motion.div
                key={activeVideo.src}
                className="absolute inset-y-0 right-0 h-full w-full overflow-hidden md:w-[80%]"
                initial={{ opacity: 0.3 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.7, ease: "easeOut" }}
              >
                <motion.video
                  className="h-full w-full object-cover object-right"
                  src={activeVideo.src}
                  autoPlay
                  muted
                  loop
                  playsInline
                  preload="metadata"
                  initial={{ scale: 1.04 }}
                  animate={{ scale: 1 }}
                  transition={{ duration: 0.7, ease: "easeOut" }}
                />
              </motion.div>
            </AnimatePresence>

            <div className="pointer-events-none absolute inset-y-0 left-0 w-full bg-gradient-to-r from-[#05080f] via-[#05080f]/95 via-45% to-transparent md:w-[66%]" />
            <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_top_left,rgba(6,182,212,0.16),transparent_34%)]" />

            <div className="relative z-10 flex h-full items-center px-6 py-8 md:px-10">
              <div className="max-w-2xl">
                <p className="text-xs font-semibold uppercase tracking-[0.32em] text-cyan-200/80">
                  Segmentação Assistido por IA
                </p>
                <h1 className="mt-4 leading-tight">
                  <img
                    src="/site/vizier_white.svg"
                    alt="Vizier"
                    className="h-12 w-auto drop-shadow-[0_0_22px_rgba(34,211,238,0.28)] md:h-16"
                    loading="eager"
                  />
                  <span className="mt-1 block text-3xl font-medium text-white md:text-5xl">
                    detectando sinais, apoiando decisões.
                  </span>
                </h1>
                <p className="mt-5 max-w-xl text-sm leading-7 text-slate-200 md:text-lg md:leading-8">
                  Assistente de IA para análise de CT e MRI que ajuda médicos a detectar anomalias, tumores e lesões e priorizar casos críticos.
                </p>

                <div className="mt-5 rounded-xl border border-white/15 bg-black/25 px-4 py-3">
                  <p className="text-xs uppercase tracking-[0.2em] text-cyan-200/70">
                    Slide ativo
                  </p>
                  <p className="mt-1 text-sm font-semibold text-white md:text-base">
                    {activeVideo.title}
                  </p>
                  <p className="mt-1 text-xs text-slate-200 md:text-sm">
                    {activeVideo.subtitle}
                  </p>
                </div>
              </div>
            </div>

            <div className="absolute bottom-4 right-4 z-20 flex gap-2 md:bottom-6 md:right-6">
              {VIDEO_SHOWCASE.map((video, index) => (
                <button
                  key={video.src}
                  type="button"
                  onClick={() => setActiveVideoIndex(index)}
                  aria-label={`Ir para slide ${index + 1}`}
                  className={`h-2.5 rounded-full transition ${
                    index === activeVideoIndex
                      ? "w-8 bg-cyan-300"
                      : "w-2.5 bg-white/60 hover:bg-white/90"
                  }`}
                />
              ))}
            </div>
          </div>
        </motion.section>

        <motion.section
          initial={{ opacity: 0, y: 14 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, amount: 0.25 }}
          transition={{ duration: 0.45 }}
          className="mt-8 rounded-[30px] border border-cyan-300/25 bg-[linear-gradient(140deg,rgba(6,18,30,0.96),rgba(4,9,18,0.95))] p-6 md:p-8"
        >
          <div className="mb-5">
            <p className="text-xs font-semibold uppercase tracking-[0.28em] text-cyan-200/80">
              Impacto Real
            </p>
            <h2 className="mt-2 text-2xl font-semibold text-white md:text-3xl">
              Performance clínica
            </h2>
          </div>

          <div className="grid gap-4 md:grid-cols-2">
            {IMPACT_HIGHLIGHTS.map((item) => (
              <article
                key={item.metric}
                className="rounded-2xl border border-white/12 bg-white/5 p-5 backdrop-blur-sm"
              >
                <p className="text-3xl font-semibold leading-none text-cyan-300 md:text-4xl">
                  {item.metric}
                </p>
                <p className="mt-3 text-lg font-semibold text-white">{item.title}</p>
                <p className="mt-2 text-sm leading-7 text-slate-200">{item.text}</p>
              </article>
            ))}
          </div>
        </motion.section>

        <section className="mt-8">
          <DataFlowVisualization />
        </section>

        <section className="mt-8 rounded-[30px] border border-white/12 bg-[linear-gradient(145deg,rgba(9,18,31,0.95),rgba(4,9,18,0.95))] p-6 md:p-8">
          <div className="mb-6">
            <p className="text-xs font-semibold uppercase tracking-[0.28em] text-cyan-200/80">
              Fale com a Vizier
            </p>
            <h2 className="mt-2 text-2xl font-semibold text-white md:text-3xl">
              Solicite uma consulta
            </h2>
            <p className="mt-3 max-w-3xl text-sm leading-7 text-slate-300 md:text-base">
              Preencha o formulário para receber contato da nossa equipe com uma
              demonstração aplicada ao seu fluxo clínico.
            </p>
          </div>

          <form onSubmit={(event) => void handleConsultationSubmit(event)} className="space-y-4">
            <div className="grid gap-4 md:grid-cols-2">
              <label className="space-y-2">
                <span className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-200">
                  NOME
                </span>
                <input
                  type="text"
                  value={consultationForm.first_name || ""}
                  onChange={(event) => updateConsultationField("first_name", event.target.value)}
                  className="w-full rounded-xl border border-white/15 bg-slate-950/50 px-3 py-2.5 text-sm text-white outline-none transition focus:border-cyan-400/65"
                />
              </label>

              <label className="space-y-2">
                <span className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-200">
                  SOBRENOME
                </span>
                <input
                  type="text"
                  value={consultationForm.last_name || ""}
                  onChange={(event) => updateConsultationField("last_name", event.target.value)}
                  className="w-full rounded-xl border border-white/15 bg-slate-950/50 px-3 py-2.5 text-sm text-white outline-none transition focus:border-cyan-400/65"
                />
              </label>
            </div>

            <div className="grid gap-4 md:grid-cols-2">
              <label className="space-y-2">
                <span className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-200">
                  NOME DA EMPRESA
                </span>
                <input
                  type="text"
                  value={consultationForm.company_name || ""}
                  onChange={(event) =>
                    updateConsultationField("company_name", event.target.value)
                  }
                  className="w-full rounded-xl border border-white/15 bg-slate-950/50 px-3 py-2.5 text-sm text-white outline-none transition focus:border-cyan-400/65"
                />
              </label>

              <label className="space-y-2">
                <span className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-200">
                  CARGO
                </span>
                <input
                  type="text"
                  value={consultationForm.job_title || ""}
                  onChange={(event) => updateConsultationField("job_title", event.target.value)}
                  className="w-full rounded-xl border border-white/15 bg-slate-950/50 px-3 py-2.5 text-sm text-white outline-none transition focus:border-cyan-400/65"
                />
              </label>
            </div>

            <div className="grid gap-4 md:grid-cols-2">
              <label className="space-y-2">
                <span className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-200">
                  SEU E-MAIL*
                </span>
                <input
                  type="email"
                  required
                  value={consultationForm.email}
                  onChange={(event) => updateConsultationField("email", event.target.value)}
                  className="w-full rounded-xl border border-white/15 bg-slate-950/50 px-3 py-2.5 text-sm text-white outline-none transition focus:border-cyan-400/65"
                />
              </label>

              <label className="space-y-2">
                <span className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-200">
                  PAÍS*
                </span>
                <select
                  required
                  value={consultationForm.country}
                  onChange={(event) => updateConsultationField("country", event.target.value)}
                  className="w-full rounded-xl border border-white/15 bg-slate-950/50 px-3 py-2.5 text-sm text-white outline-none transition focus:border-cyan-400/65"
                >
                  <option value="">Selecione um país</option>
                  {COUNTRY_OPTIONS.map((country) => (
                    <option key={country.code} value={country.label}>
                      {country.label}
                    </option>
                  ))}
                </select>
              </label>
            </div>

            <div className="grid gap-4 md:grid-cols-2">
              <label className="space-y-2">
                <span className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-200">
                  MENSAGEM
                </span>
                <textarea
                  value={consultationForm.message || ""}
                  onChange={(event) => updateConsultationField("message", event.target.value)}
                  className="min-h-[120px] w-full rounded-xl border border-white/15 bg-slate-950/50 px-3 py-2.5 text-sm text-white outline-none transition focus:border-cyan-400/65"
                />
              </label>

              <label className="space-y-2">
                <span className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-200">
                  COMO VOCÊ FICOU SABENDO DE NÓS?
                </span>
                <textarea
                  value={consultationForm.discovery_source || ""}
                  onChange={(event) =>
                    updateConsultationField("discovery_source", event.target.value)
                  }
                  className="min-h-[120px] w-full rounded-xl border border-white/15 bg-slate-950/50 px-3 py-2.5 text-sm text-white outline-none transition focus:border-cyan-400/65"
                />
              </label>
            </div>

            <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
              <button
                type="submit"
                disabled={submittingConsultation}
                className="inline-flex items-center justify-center rounded-full bg-cyan-500 px-6 py-2.5 text-sm font-semibold text-slate-950 transition hover:bg-cyan-400 disabled:cursor-not-allowed disabled:opacity-70"
              >
                {submittingConsultation ? "Enviando..." : "Solicitar consulta"}
              </button>

              {consultationSuccess ? (
                <p className="text-sm text-emerald-300">{consultationSuccess}</p>
              ) : null}
              {consultationError ? (
                <p className="text-sm text-rose-300">{consultationError}</p>
              ) : null}
            </div>
          </form>
        </section>
      </main>

      <footer className="border-t border-white/10 bg-slate-950/80">
        <div className="mx-auto flex w-full max-w-7xl flex-col gap-2 px-4 py-5 text-sm text-slate-300 md:flex-row md:items-center md:justify-between md:px-8">
          <span>Vizier Med AI · Detecção e segmentação para CT e MRI</span>
          <div className="flex flex-col gap-1 md:flex-row md:gap-6">
            <a href="mailto:vizier.med@gmail.com" className="hover:text-cyan-200">
              vizier.med@gmail.com
            </a>
            <a
              href="https://wa.me/5519998277864"
              target="_blank"
              rel="noreferrer"
              className="hover:text-cyan-200"
            >
              WhatsApp: (19) 99827-7864
            </a>
          </div>
        </div>
      </footer>
    </div>
  );
}

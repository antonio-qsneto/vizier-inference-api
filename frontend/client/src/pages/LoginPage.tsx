import { useEffect, useState } from "react";
import { useLocation } from "wouter";
import { motion } from "framer-motion";
import { ArrowRight, KeyRound, ServerCog } from "lucide-react";
import { fetchHealth } from "@/api/services";
import { useAuth } from "@/auth/AuthContext";
import { env, isCognitoConfigured } from "@/env";
import { Panel } from "@/components/primitives";

export default function LoginPage() {
  const [, navigate] = useLocation();
  const { signIn, status, error } = useAuth();
  const [healthLabel, setHealthLabel] = useState("Checking backend...");

  useEffect(() => {
    let isActive = true;

    async function run() {
      try {
        const health = await fetchHealth();
        if (isActive) {
          setHealthLabel(`${health.service} ${health.version} · ${health.status}`);
        }
      } catch {
        if (isActive) {
          setHealthLabel("Backend unavailable");
        }
      }
    }

    void run();

    return () => {
      isActive = false;
    };
  }, []);

  useEffect(() => {
    if (status === "authenticated") {
      navigate("/dashboard");
    }
  }, [navigate, status]);

  return (
    <div className="min-h-screen bg-[radial-gradient(circle_at_top_left,rgba(1,149,248,0.28),transparent_26%),radial-gradient(circle_at_bottom_right,rgba(14,165,233,0.2),transparent_24%),linear-gradient(180deg,#222223,#17181b)] px-4 py-10 text-white md:px-8">
      <div className="mx-auto grid min-h-[calc(100vh-5rem)] max-w-7xl gap-6 lg:grid-cols-[1.1fr_0.9fr]">
        <motion.section
          initial={{ opacity: 0, y: 18 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.45 }}
          className="rounded-[34px] border border-white/10 bg-[linear-gradient(180deg,rgba(37,37,40,0.96),rgba(20,20,24,0.92))] p-8 shadow-[0_30px_80px_rgba(0,0,0,0.34)]"
        >
          <p className="text-xs font-semibold uppercase tracking-[0.32em] text-sky-300/75">
            Vizier Med
          </p>
          <h1 className="mt-5 max-w-2xl text-4xl font-semibold tracking-tight text-white sm:text-5xl">
            Frontend clínico reconstruído para os endpoints reais do backend.
          </h1>
          <p className="mt-6 max-w-2xl text-base leading-8 text-slate-300">
            Auth via Cognito Hosted UI, clinic workflow, upload de estudos com
            catálogo dinâmico e viewer PACS para `image.nii.gz` + `mask.nii.gz`.
          </p>

          <div className="mt-8 flex flex-wrap gap-3">
            <button
              type="button"
              onClick={() => void signIn("login")}
              className="inline-flex items-center gap-2 rounded-full bg-sky-500 px-5 py-3 text-sm font-semibold text-white transition hover:bg-sky-400"
            >
              <KeyRound className="h-4 w-4" />
              {isCognitoConfigured ? "Entrar com Cognito" : "Entrar em modo local"}
            </button>
            <button
              type="button"
              onClick={() => void signIn("signup")}
              className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/6 px-5 py-3 text-sm font-semibold text-slate-100 transition hover:bg-white/10"
            >
              Criar conta
              <ArrowRight className="h-4 w-4" />
            </button>
          </div>

          <div className="mt-8 grid gap-4 sm:grid-cols-3">
            {[
              {
                label: "Backend",
                value: env.apiBaseUrl,
                detail: healthLabel,
              },
              {
                label: "Auth mode",
                value: isCognitoConfigured ? "Hosted UI + PKCE" : "Development bearer",
                detail:
                  "O frontend usa o token Bearer contra /api/auth/users/me/ e todos os endpoints protegidos.",
              },
              {
                label: "Viewer",
                value: "Tri-planar PACS",
                detail:
                  "Carrega `result/` e faz proxy de `file://` local em ambiente de desenvolvimento.",
              },
            ].map((item) => (
              <Panel key={item.label} className="space-y-3 p-5">
                <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-400">
                  {item.label}
                </p>
                <p className="text-lg font-semibold text-white">{item.value}</p>
                <p className="text-sm leading-6 text-slate-300">{item.detail}</p>
              </Panel>
            ))}
          </div>

          {error ? (
            <p className="mt-6 rounded-2xl border border-rose-400/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-100">
              {error}
            </p>
          ) : null}
        </motion.section>

        <motion.section
          initial={{ opacity: 0, x: 18 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ duration: 0.5, delay: 0.08 }}
          className="grid gap-6"
        >
          <Panel className="space-y-5">
            <div className="inline-flex h-11 w-11 items-center justify-center rounded-2xl bg-sky-500/15 text-sky-200">
              <ServerCog className="h-5 w-5" />
            </div>
            <div className="space-y-3">
              <h2 className="text-2xl font-semibold tracking-tight text-white">
                Fluxos conectados ao Django
              </h2>
              <p className="text-sm leading-7 text-slate-300">
                O app agora usa os contratos reais: `exam_modality` +
                `category_id` no upload, `users/me/` para perfil, `clinics/*`
                para tenancy e `studies/:id/result/` para assets de
                visualização.
              </p>
            </div>
            <ul className="space-y-3 text-sm text-slate-200">
              <li className="rounded-2xl border border-white/10 bg-white/5 px-4 py-3">
                Modality dropdown usa `GET /api/auth/categories/` como source of truth.
              </li>
              <li className="rounded-2xl border border-white/10 bg-white/5 px-4 py-3">
                Clinic management cobre criação, convite, aceite e remoção de médicos.
              </li>
              <li className="rounded-2xl border border-white/10 bg-white/5 px-4 py-3">
                Study monitor faz polling em `/status/` até `COMPLETED` ou `FAILED`.
              </li>
            </ul>
          </Panel>

          <Panel className="space-y-4">
            <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-400">
              Session notes
            </p>
            <p className="text-sm leading-7 text-slate-300">
              Em ambiente local sem Cognito configurado, o frontend entra em modo
              de desenvolvimento e usa um Bearer token simples para acionar o
              fallback do backend.
            </p>
            <p className="text-sm leading-7 text-slate-300">
              Com Cognito configurado, o callback usa Authorization Code + PKCE e
              persiste somente os dados necessários de sessão.
            </p>
          </Panel>
        </motion.section>
      </div>
    </div>
  );
}

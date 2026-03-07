import { useEffect, useState } from "react";
import { useLocation } from "wouter";
import { motion } from "framer-motion";
import { ArrowRight, KeyRound, ServerCog } from "lucide-react";
import { fetchHealth } from "@/api/services";
import { consumeAuthNotice } from "@/auth/session";
import { useAuth } from "@/auth/AuthContext";
import { env } from "@/env";
import { Panel } from "@/components/primitives";

export default function LoginPage() {
  const [, navigate] = useLocation();
  const {
    signIn,
    signInDevMock,
    signUpDevMock,
    status,
    error,
    isCognitoConfigured,
    isDevMockAuthEnabled,
  } = useAuth();
  const [healthLabel, setHealthLabel] = useState("Checking backend...");
  const [notice, setNotice] = useState<string | null>(null);
  const [devEmail, setDevEmail] = useState("dev@example.com");
  const [devPassword, setDevPassword] = useState("dev-password-123");
  const [devFirstName, setDevFirstName] = useState("Dev");
  const [devLastName, setDevLastName] = useState("User");
  const [devAction, setDevAction] = useState<"login" | "signup" | null>(null);
  const [devError, setDevError] = useState<string | null>(null);

  useEffect(() => {
    let isActive = true;

    async function run() {
      try {
        const health = await fetchHealth();
        if (isActive) {
          setHealthLabel(
            `${health.service} ${health.version} · ${health.status}`,
          );
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
    setNotice(consumeAuthNotice());
  }, []);

  useEffect(() => {
    if (status === "authenticated") {
      navigate("/dashboard");
    }
  }, [navigate, status]);

  async function handleDevLogin() {
    if (!devEmail.trim() || !devPassword) {
      setDevError("Informe e-mail e senha para login dev.");
      return;
    }

    setDevError(null);
    setDevAction("login");
    try {
      await signInDevMock({
        email: devEmail.trim().toLowerCase(),
        password: devPassword,
      });
    } catch {
      // Error message is handled by AuthContext.
    } finally {
      setDevAction(null);
    }
  }

  async function handleDevSignup() {
    if (!devEmail.trim() || !devPassword) {
      setDevError("Informe e-mail e senha para criar cadastro dev.");
      return;
    }

    setDevError(null);
    setDevAction("signup");
    try {
      await signUpDevMock({
        email: devEmail.trim().toLowerCase(),
        password: devPassword,
        first_name: devFirstName.trim(),
        last_name: devLastName.trim(),
      });
    } catch {
      // Error message is handled by AuthContext.
    } finally {
      setDevAction(null);
    }
  }

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

          {isCognitoConfigured ? (
            <div className="mt-8 flex flex-wrap gap-3">
              <button
                type="button"
                onClick={() => void signIn("login")}
                className="inline-flex items-center gap-2 rounded-full bg-sky-500 px-5 py-3 text-sm font-semibold text-white transition hover:bg-sky-400"
              >
                <KeyRound className="h-4 w-4" />
                Entrar com Cognito
              </button>
              <button
                type="button"
                onClick={() => void signIn("signup")}
                className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/6 px-5 py-3 text-sm font-semibold text-slate-100 transition hover:bg-white/10"
              >
                Criar conta Cognito
                <ArrowRight className="h-4 w-4" />
              </button>
            </div>
          ) : (
            <div className="mt-8 flex flex-wrap gap-3">
              <button
                type="button"
                onClick={() => void signIn("login")}
                className="inline-flex items-center gap-2 rounded-full bg-sky-500 px-5 py-3 text-sm font-semibold text-white transition hover:bg-sky-400"
              >
                <KeyRound className="h-4 w-4" />
                Entrar em modo local
              </button>
            </div>
          )}

          {isDevMockAuthEnabled ? (
            <Panel className="mt-8 space-y-4 border border-sky-400/20 bg-sky-500/5 p-5">
              <div className="space-y-1">
                <p className="text-xs font-semibold uppercase tracking-[0.24em] text-sky-200/80">
                  Development mock auth
                </p>
                <p className="text-sm text-slate-300">
                  Cadastro e login local sem passar pelo Cognito.
                </p>
              </div>

              <div className="grid gap-3 sm:grid-cols-2">
                <input
                  type="email"
                  value={devEmail}
                  onChange={(event) => setDevEmail(event.target.value)}
                  placeholder="E-mail dev"
                  className="rounded-xl border border-white/15 bg-[#21232a] px-3 py-2 text-sm text-white outline-none transition focus:border-sky-400/60"
                />
                <input
                  type="password"
                  value={devPassword}
                  onChange={(event) => setDevPassword(event.target.value)}
                  placeholder="Senha dev"
                  className="rounded-xl border border-white/15 bg-[#21232a] px-3 py-2 text-sm text-white outline-none transition focus:border-sky-400/60"
                />
                <input
                  type="text"
                  value={devFirstName}
                  onChange={(event) => setDevFirstName(event.target.value)}
                  placeholder="Primeiro nome (opcional)"
                  className="rounded-xl border border-white/15 bg-[#21232a] px-3 py-2 text-sm text-white outline-none transition focus:border-sky-400/60"
                />
                <input
                  type="text"
                  value={devLastName}
                  onChange={(event) => setDevLastName(event.target.value)}
                  placeholder="Sobrenome (opcional)"
                  className="rounded-xl border border-white/15 bg-[#21232a] px-3 py-2 text-sm text-white outline-none transition focus:border-sky-400/60"
                />
              </div>

              <div className="flex flex-wrap gap-3">
                <button
                  type="button"
                  onClick={() => void handleDevLogin()}
                  disabled={devAction !== null}
                  className="inline-flex items-center gap-2 rounded-full bg-emerald-500 px-5 py-2.5 text-sm font-semibold text-white transition hover:bg-emerald-400 disabled:cursor-not-allowed disabled:opacity-70"
                >
                  Entrar no modo dev
                </button>
                <button
                  type="button"
                  onClick={() => void handleDevSignup()}
                  disabled={devAction !== null}
                  className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/6 px-5 py-2.5 text-sm font-semibold text-slate-100 transition hover:bg-white/10 disabled:cursor-not-allowed disabled:opacity-70"
                >
                  Criar cadastro dev
                </button>
              </div>

              {devError ? (
                <p className="rounded-xl border border-rose-400/30 bg-rose-500/10 px-3 py-2 text-sm text-rose-100">
                  {devError}
                </p>
              ) : null}
            </Panel>
          ) : null}

          <div className="mt-8 grid gap-4 sm:grid-cols-3">
            {[
              {
                label: "Backend",
                value: env.apiBaseUrl,
                detail: healthLabel,
              },
              {
                label: "Auth mode",
                value: isCognitoConfigured
                  ? "Hosted UI + PKCE + Dev mock"
                  : "Development bearer + Dev mock",
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
                <p className="text-sm leading-6 text-slate-300">
                  {item.detail}
                </p>
              </Panel>
            ))}
          </div>

          {error ? (
            <p className="mt-6 rounded-2xl border border-rose-400/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-100">
              {error}
            </p>
          ) : null}

          {notice ? (
            <p className="mt-6 rounded-2xl border border-emerald-400/30 bg-emerald-500/10 px-4 py-3 text-sm text-emerald-100">
              {notice}
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
                Modality dropdown usa `GET /api/auth/categories/` como source of
                truth.
              </li>
              <li className="rounded-2xl border border-white/10 bg-white/5 px-4 py-3">
                Clinic management cobre criação, convite, aceite e remoção de
                médicos.
              </li>
              <li className="rounded-2xl border border-white/10 bg-white/5 px-4 py-3">
                Study monitor faz polling em `/status/` até `COMPLETED` ou
                `FAILED`.
              </li>
            </ul>
          </Panel>

          <Panel className="space-y-4">
            <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-400">
              Session notes
            </p>
            <p className="text-sm leading-7 text-slate-300">
              O login Cognito continua disponível via Hosted UI + PKCE para
              fluxo real de autenticação.
            </p>
            <p className="text-sm leading-7 text-slate-300">
              Em desenvolvimento, o frontend também permite criar cadastro e
              fazer login mock local, sem passar pelo Cognito.
            </p>
          </Panel>
        </motion.section>
      </div>
    </div>
  );
}

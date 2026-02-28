import { useEffect, useState } from "react";
import { useLocation } from "wouter";
import { LoaderCircle } from "lucide-react";
import { Panel } from "@/components/primitives";
import { useAuth } from "@/auth/AuthContext";

export default function AuthCallbackPage() {
  const [, navigate] = useLocation();
  const { completeHostedUiLogin } = useAuth();
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let isActive = true;

    async function run() {
      try {
        await completeHostedUiLogin(new URLSearchParams(window.location.search));
        if (isActive) {
          navigate("/dashboard");
        }
      } catch (callbackError) {
        if (!isActive) {
          return;
        }
        if (callbackError instanceof Error) {
          setError(callbackError.message);
        } else {
          setError("Authentication callback failed");
        }
      }
    }

    void run();

    return () => {
      isActive = false;
    };
  }, [completeHostedUiLogin, navigate]);

  return (
    <div className="flex min-h-screen items-center justify-center bg-[linear-gradient(180deg,#222223,#17181b)] px-4">
      <Panel className="w-full max-w-lg space-y-5 text-center">
        {error ? (
          <>
            <p className="text-sm font-semibold uppercase tracking-[0.24em] text-rose-200">
              Authentication failed
            </p>
            <h1 className="text-2xl font-semibold text-white">{error}</h1>
            <button
              type="button"
              onClick={() => navigate("/login")}
              className="rounded-full bg-sky-500 px-5 py-3 text-sm font-semibold text-white transition hover:bg-sky-400"
            >
              Voltar ao login
            </button>
          </>
        ) : (
          <>
            <LoaderCircle className="mx-auto h-8 w-8 animate-spin text-sky-300" />
            <p className="text-sm font-semibold uppercase tracking-[0.24em] text-sky-200">
              Cognito callback
            </p>
            <h1 className="text-2xl font-semibold text-white">
              Concluindo autenticação e carregando o workspace...
            </h1>
          </>
        )}
      </Panel>
    </div>
  );
}

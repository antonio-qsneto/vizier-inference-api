import { useEffect, useState } from "react";
import { Link } from "wouter";
import { toast } from "sonner";
import { ApiError } from "@/api/client";
import { syncIndividualBilling } from "@/api/services";
import { useAuth } from "@/auth/AuthContext";
import { startBillingPortal } from "@/billing/adapter";
import { Panel } from "@/components/primitives";

const FREE_PLAN = "free";
const WEBHOOK_SYNC_ATTEMPTS = 8;
const WEBHOOK_SYNC_DELAY_MS = 1500;

function wait(ms: number) {
  return new Promise((resolve) => {
    setTimeout(resolve, ms);
  });
}

export default function BillingResultPage({
  status,
}: {
  status: "success" | "cancel";
}) {
  const isSuccess = status === "success";
  const { accessToken, refreshProfile, user } = useAuth();
  const [syncingProfile, setSyncingProfile] = useState(isSuccess);
  const [openingPortal, setOpeningPortal] = useState(false);
  const effectiveRole =
    user?.effective_role ||
    (user?.role === "CLINIC_ADMIN"
      ? "clinic_admin"
      : user?.role === "CLINIC_DOCTOR"
        ? "clinic_doctor"
        : "individual");
  const isIndividualUser = effectiveRole === "individual" && !user?.clinic_id;
  const currentPlan = user?.subscription_plan || FREE_PLAN;

  useEffect(() => {
    if (!isSuccess || !isIndividualUser || !accessToken) {
      setSyncingProfile(false);
      return;
    }

    const token = accessToken;
    const checkoutSessionId =
      new URLSearchParams(window.location.search).get("session_id") || undefined;
    let isCancelled = false;

    async function syncProfileAfterCheckout() {
      setSyncingProfile(true);

      for (let attempt = 0; attempt < WEBHOOK_SYNC_ATTEMPTS; attempt += 1) {
        try {
          await syncIndividualBilling(token, checkoutSessionId);
          if (isCancelled) {
            return;
          }
          await refreshProfile();
          setSyncingProfile(false);
          return;
        } catch (requestError) {
          const shouldRetry =
            requestError instanceof ApiError &&
            requestError.status === 409 &&
            attempt < WEBHOOK_SYNC_ATTEMPTS - 1;
          if (shouldRetry) {
            await wait(WEBHOOK_SYNC_DELAY_MS);
            continue;
          }
          if (!isCancelled) {
            toast.error(
              requestError instanceof Error
                ? requestError.message
                : "Falha ao sincronizar assinatura após checkout",
            );
            await refreshProfile();
          }
          setSyncingProfile(false);
          return;
        }
      }

      setSyncingProfile(false);
    }

    void syncProfileAfterCheckout();

    return () => {
      isCancelled = true;
    };
  }, [accessToken, isSuccess, isIndividualUser, refreshProfile]);

  async function handleOpenPortal() {
    try {
      setOpeningPortal(true);
      const portalUrl = await startBillingPortal(accessToken);
      window.location.assign(portalUrl);
    } catch (requestError) {
      toast.error(
        requestError instanceof Error
          ? requestError.message
          : "Falha ao abrir portal do Stripe",
      );
    } finally {
      setOpeningPortal(false);
    }
  }

  return (
    <div className="flex min-h-[70vh] items-center justify-center">
      <Panel className="w-full max-w-2xl space-y-5 text-center">
        <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-400">
          Billing return
        </p>
        <h1 className="text-3xl font-semibold text-white">
          {isSuccess
            ? "Checkout Stripe concluído"
            : "Checkout Stripe cancelado"}
        </h1>
        <p className="text-sm leading-7 text-slate-300">
          {isSuccess
            ? "Estamos sincronizando sua assinatura com o Stripe para refletir o plano imediatamente."
            : "O plano não foi alterado. Você pode voltar ao billing e tentar novamente."}
        </p>

        {isSuccess ? (
          <p className="text-sm text-slate-300">
            Plano atual: <span className="font-semibold text-white">{currentPlan}</span>
          </p>
        ) : null}

        {isSuccess && syncingProfile ? (
          <p className="text-xs uppercase tracking-[0.2em] text-sky-300/80">
            Sincronizando assinatura...
          </p>
        ) : null}

        {isSuccess && isIndividualUser ? (
          <button
            type="button"
            onClick={() => void handleOpenPortal()}
            disabled={openingPortal}
            className="inline-flex rounded-full border border-white/10 bg-white/6 px-5 py-3 text-sm font-semibold text-white transition hover:bg-white/10 disabled:cursor-not-allowed disabled:opacity-70"
          >
            {openingPortal
              ? "Abrindo portal..."
              : "Gerenciar/cancelar assinatura no Stripe"}
          </button>
        ) : null}

        <Link href="/billing">
          <a className="inline-flex rounded-full bg-sky-500 px-5 py-3 text-sm font-semibold text-white transition hover:bg-sky-400">
            Back to billing
          </a>
        </Link>
      </Panel>
    </div>
  );
}

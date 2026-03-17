import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { toast } from "sonner";
import { Link } from "wouter";
import { useAuth } from "@/auth/AuthContext";
import {
  type BillingPlan,
  billingPlans,
  startBillingCheckout,
  startBillingPortal,
} from "@/billing/adapter";
import { InlineNotice, PageIntro, Panel } from "@/components/primitives";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

function matchesCurrentPlan(
  currentPlan: string | null | undefined,
  candidate: string,
) {
  return (currentPlan || "free") === candidate;
}

function normalizePlanId(
  plan: string | null | undefined,
): BillingPlan["id"] {
  if (plan === "plano_individual_mensal") {
    return "plano_individual_mensal";
  }
  if (plan === "plano_individual_anual") {
    return "plano_individual_anual";
  }
  return "free";
}

function isPaidPlan(planId: BillingPlan["id"]) {
  return planId !== "free";
}

export default function BillingPage() {
  const { accessToken, user, refreshProfile } = useAuth();
  const [openingPortal, setOpeningPortal] = useState(false);
  const [pendingPlanChange, setPendingPlanChange] = useState<BillingPlan | null>(
    null,
  );
  const [confirmPassword, setConfirmPassword] = useState("");
  const [confirmingPlanChange, setConfirmingPlanChange] = useState(false);
  const effectiveRole =
    user?.effective_role ||
    (user?.role === "CLINIC_ADMIN"
      ? "clinic_admin"
      : user?.role === "CLINIC_DOCTOR"
        ? "clinic_doctor"
        : "individual");
  const isIndividualUser = effectiveRole === "individual" && !user?.clinic_id;
  const currentPlanId = normalizePlanId(user?.subscription_plan);
  const isIndividualFreeUser = isIndividualUser && currentPlanId === "free";
  const isIndividualSubscriber = isIndividualUser && isPaidPlan(currentPlanId);

  useEffect(() => {
    void refreshProfile();
  }, [refreshProfile]);

  async function executePlanSelection(
    planId: "free" | "plano_individual_mensal" | "plano_individual_anual",
    currentPassword?: string,
  ) {
    if (planId === "free") {
      toast.message("Plano free não exige checkout.");
      return;
    }

    try {
      const result = await startBillingCheckout({
        planId,
        token: accessToken,
        user,
        currentPassword,
      });

      if (result.message) {
        toast.message(result.message);
      }

      if (result.mode === "redirect") {
        window.location.assign(result.url);
        return;
      }

      await refreshProfile();
      if (result.mode === "updated") {
        toast.success("Plano atualizado com sucesso.");
      }
    } catch (requestError) {
      toast.error(
        requestError instanceof Error
          ? requestError.message
          : "Billing start failed",
      );
    }
  }

  async function handleSelectPlan(
    planId: "free" | "plano_individual_mensal" | "plano_individual_anual",
  ) {
    if (planId === "free") {
      toast.message("Plano free não exige checkout.");
      return;
    }

    const isSwitchingBetweenPaidPlans =
      isPaidPlan(currentPlanId) &&
      isPaidPlan(planId) &&
      currentPlanId !== planId;

    if (isSwitchingBetweenPaidPlans) {
      const targetPlan = billingPlans.find((plan) => plan.id === planId) || null;
      setPendingPlanChange(targetPlan);
      setConfirmPassword("");
      return;
    }

    await executePlanSelection(planId);
  }

  async function handleConfirmPlanChange() {
    if (!pendingPlanChange) {
      return;
    }
    if (!confirmPassword) {
      toast.error("Informe sua senha para confirmar a troca de plano.");
      return;
    }

    try {
      setConfirmingPlanChange(true);
      await executePlanSelection(pendingPlanChange.id, confirmPassword);
      setPendingPlanChange(null);
      setConfirmPassword("");
    } finally {
      setConfirmingPlanChange(false);
    }
  }

  async function handleOpenPortal() {
    try {
      setOpeningPortal(true);
      const portalUrl = await startBillingPortal(accessToken);
      window.location.assign(portalUrl);
    } catch (requestError) {
      toast.error(
        requestError instanceof Error
          ? requestError.message
          : "Failed to open billing portal",
      );
    } finally {
      setOpeningPortal(false);
    }
  }

  return (
    <motion.section
      initial={{ opacity: 0, y: 18 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35 }}
      className="space-y-6"
    >
      <PageIntro
        eyebrow="Billing"
        title="Assinatura individual Stripe"
        description="Usuário individual começa no plano free (sem upload). Para habilitar upload, assine o plano mensal ou anual."
      />

      <InlineNotice title="Integration note">
        O checkout abre no Stripe e o backend atualiza o plano via webhook em
        `/api/auth/billing/webhook/`.
      </InlineNotice>

      {!isIndividualUser ? (
        <InlineNotice title="Plano individual">
          Esta tela de assinatura Stripe está habilitada apenas para usuários
          individuais sem vínculo com clínica.
        </InlineNotice>
      ) : null}

      {isIndividualFreeUser ? (
        <InlineNotice title="Quer plano de clínica?">
          Para ativar cobrança por assentos (múltiplos médicos), use o fluxo de upgrade em{" "}
          <Link href="/clinic">
            <a className="font-semibold text-sky-200 underline">Clinic</a>
          </Link>
          .
        </InlineNotice>
      ) : null}

      {isIndividualUser ? (
        <>
          {isIndividualSubscriber ? (
            <div className="flex flex-wrap gap-3">
              <button
                type="button"
                onClick={() => void handleOpenPortal()}
                disabled={openingPortal}
                className="rounded-2xl border border-white/10 bg-white/6 px-5 py-3 text-sm font-semibold text-slate-100 transition hover:bg-white/10 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {openingPortal
                  ? "Abrindo portal..."
                  : "Gerenciar/cancelar assinatura no Stripe"}
              </button>
            </div>
          ) : null}

          <div className="grid gap-5 xl:grid-cols-3">
            {billingPlans.map((plan) => {
              const isCurrent = matchesCurrentPlan(
                user?.subscription_plan,
                plan.id,
              );
              const isFree = plan.id === "free";
              return (
                <Panel
                  key={plan.id}
                  className={
                    isCurrent
                      ? "border-sky-300/30 shadow-[0_30px_90px_rgba(1,149,248,0.18)]"
                      : undefined
                  }
                >
                  <div className="space-y-5">
                    <div className="space-y-3">
                      <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-400">
                        {plan.label}
                      </p>
                      {plan.id === "plano_individual_anual" ? (
                        <p className="inline-flex rounded-full border border-emerald-300/40 bg-emerald-500/15 px-3 py-1 text-xs font-semibold uppercase tracking-[0.18em] text-emerald-200">
                          10% de desconto
                        </p>
                      ) : null}
                      <h2 className="text-3xl font-semibold text-white">
                        {plan.priceLabel}
                      </h2>
                      <p className="text-sm leading-7 text-slate-300">
                        {plan.summary}
                      </p>
                    </div>

                    <div className="space-y-2">
                      {plan.features.map((feature) => (
                        <div
                          key={feature}
                          className="rounded-2xl border border-white/10 bg-white/5 px-4 py-3 text-sm text-slate-200"
                        >
                          {feature}
                        </div>
                      ))}
                    </div>

                    <button
                      type="button"
                      onClick={() => void handleSelectPlan(plan.id)}
                      disabled={isCurrent || isFree}
                      className={
                        isCurrent
                          ? "rounded-2xl border border-white/10 bg-white/6 px-5 py-3 text-sm font-semibold text-slate-100 transition"
                          : isFree
                            ? "rounded-2xl border border-white/10 bg-white/6 px-5 py-3 text-sm font-semibold text-slate-400 transition"
                            : "rounded-2xl bg-sky-500 px-5 py-3 text-sm font-semibold text-white transition hover:bg-sky-400"
                      }
                    >
                      {isCurrent
                        ? "Plano atual"
                        : isFree
                          ? "Plano base"
                          : "Assinar plano"}
                    </button>
                  </div>
                </Panel>
              );
            })}
          </div>
        </>
      ) : effectiveRole === "clinic_admin" ? (
        <InlineNotice title="Gerenciamento de clínica">
          Contas admin de clínica gerenciam assinatura e cancelamento na página{" "}
          <Link href="/clinic">
            <a className="font-semibold text-sky-200 underline">Clinic</a>
          </Link>
          .
        </InlineNotice>
      ) : (
        <InlineNotice title="Billing indisponível">
          Desvincule-se da clínica para voltar ao plano free individual e acessar
          os planos de billing.
        </InlineNotice>
      )}

      <Dialog
        open={Boolean(pendingPlanChange)}
        onOpenChange={(open) => {
          if (!open && !confirmingPlanChange) {
            setPendingPlanChange(null);
            setConfirmPassword("");
          }
        }}
      >
        <DialogContent className="border-white/12 bg-[#191b20] text-white">
          <DialogHeader>
            <DialogTitle>Confirmar troca de plano</DialogTitle>
            <DialogDescription className="text-slate-300">
              Você está alterando sua assinatura para{" "}
              <span className="font-semibold text-white">
                {pendingPlanChange?.label}
              </span>{" "}
              no valor de{" "}
              <span className="font-semibold text-white">
                {pendingPlanChange?.priceLabel}
              </span>
              .
            </DialogDescription>
          </DialogHeader>

          {pendingPlanChange?.id === "plano_individual_anual" ? (
            <p className="rounded-xl border border-emerald-300/30 bg-emerald-500/10 px-3 py-2 text-sm text-emerald-100">
              Este plano anual aplica 10% de desconto.
            </p>
          ) : null}

          <div className="space-y-2">
            <label className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-400">
              Confirme sua senha
            </label>
            <input
              type="password"
              value={confirmPassword}
              onChange={(event) => setConfirmPassword(event.target.value)}
              placeholder="Digite sua senha"
              className="w-full rounded-xl border border-white/15 bg-[#21232a] px-3 py-2 text-sm text-white outline-none transition focus:border-sky-400/60"
            />
          </div>

          <DialogFooter>
            <button
              type="button"
              onClick={() => {
                if (!confirmingPlanChange) {
                  setPendingPlanChange(null);
                  setConfirmPassword("");
                }
              }}
              disabled={confirmingPlanChange}
              className="rounded-xl border border-white/10 bg-white/6 px-4 py-2 text-sm font-semibold text-slate-200 transition hover:bg-white/10 disabled:cursor-not-allowed disabled:opacity-60"
            >
              Cancelar
            </button>
            <button
              type="button"
              onClick={() => void handleConfirmPlanChange()}
              disabled={confirmingPlanChange}
              className="rounded-xl bg-sky-500 px-4 py-2 text-sm font-semibold text-white transition hover:bg-sky-400 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {confirmingPlanChange
                ? "Confirmando..."
                : "Confirmar troca de plano"}
            </button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </motion.section>
  );
}

import { motion } from "framer-motion";
import { toast } from "sonner";
import { useAuth } from "@/auth/AuthContext";
import {
  billingPlans,
  startBillingCheckout,
} from "@/billing/adapter";
import { InlineNotice, PageIntro, Panel } from "@/components/primitives";

function matchesCurrentPlan(currentPlan: string | null | undefined, candidate: string) {
  if (!currentPlan) {
    return candidate === "free";
  }

  if (currentPlan === "starter") {
    return candidate === "professional";
  }

  if (currentPlan === "enterprise") {
    return candidate === "clinical";
  }

  return currentPlan === candidate;
}

export default function BillingPage() {
  const { accessToken, user } = useAuth();

  async function handleSelectPlan(planId: "free" | "professional" | "clinical") {
    try {
      const result = await startBillingCheckout({
        planId,
        token: accessToken,
        user,
      });

      if (result.message) {
        toast.message(result.message);
      }

      window.location.assign(result.url);
    } catch (requestError) {
      toast.error(requestError instanceof Error ? requestError.message : "Billing start failed");
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
        title="Plan selection and checkout adapter"
        description="O backend atual não expõe endpoints Stripe. Esta página já deixa o frontend pronto para plugar um checkout endpoint configurável ou cair em mock local."
      />

      <InlineNotice title="Integration note">
        `SubscriptionPlan` e `Subscription` existem no backend, mas este repositório
        ainda não expõe endpoints de checkout. O adaptador usa `VITE_ENABLE_BILLING`
        + `VITE_BILLING_CHECKOUT_ENDPOINT` quando disponíveis.
      </InlineNotice>

      <div className="grid gap-5 xl:grid-cols-3">
        {billingPlans.map((plan) => {
          const isCurrent = matchesCurrentPlan(user?.subscription_plan, plan.id);
          return (
            <Panel
              key={plan.id}
              className={isCurrent ? "border-sky-300/30 shadow-[0_30px_90px_rgba(1,149,248,0.18)]" : undefined}
            >
              <div className="space-y-5">
                <div className="space-y-3">
                  <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-400">
                    {plan.label}
                  </p>
                  <h2 className="text-3xl font-semibold text-white">{plan.priceLabel}</h2>
                  <p className="text-sm leading-7 text-slate-300">{plan.summary}</p>
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
                  className={
                    isCurrent
                      ? "rounded-2xl border border-white/10 bg-white/6 px-5 py-3 text-sm font-semibold text-slate-100 transition hover:bg-white/10"
                      : "rounded-2xl bg-sky-500 px-5 py-3 text-sm font-semibold text-white transition hover:bg-sky-400"
                  }
                >
                  {isCurrent ? "Current plan" : "Select plan"}
                </button>
              </div>
            </Panel>
          );
        })}
      </div>
    </motion.section>
  );
}

import { env, isBillingConfigured } from "@/env";
import type { UserProfile } from "@/types/api";

export interface BillingPlan {
  id: "free" | "plano_individual_mensal" | "plano_individual_anual";
  label: string;
  priceLabel: string;
  summary: string;
  features: string[];
}

export interface BillingCheckoutResult {
  mode: "redirect" | "mock" | "updated";
  url: string;
  message?: string;
}

export const billingPlans: BillingPlan[] = [
  {
    id: "free",
    label: "Free",
    priceLabel: "R$ 0",
    summary: "Acesso sem assinatura para navegação básica.",
    features: ["Sem upload de estudos", "Sem cobrança", "Upgrade opcional"],
  },
  {
    id: "plano_individual_mensal",
    label: "Plano individual mensal",
    priceLabel: "R$ 679,00/mês",
    summary: "Libera upload e processamento para usuário individual.",
    features: [
      "Upload habilitado",
      "Acesso mensal",
      "Gestão via Stripe portal",
    ],
  },
  {
    id: "plano_individual_anual",
    label: "Plano individual anual",
    priceLabel: "R$ 7.333,00/ano",
    summary: "Plano anual com upload liberado para todo o período e 10% de desconto.",
    features: [
      "Upload habilitado",
      "Ciclo anual",
      "10% de desconto em relação ao mensal",
      "Gestão via Stripe portal",
    ],
  },
];

interface CheckoutInput {
  planId: BillingPlan["id"];
  token: string | null;
  user: UserProfile | null;
  currentPassword?: string;
}

export async function startBillingCheckout({
  planId,
  token,
  currentPassword,
}: CheckoutInput): Promise<BillingCheckoutResult> {
  if (planId === "free") {
    return {
      mode: "mock",
      url: "/billing",
      message: "Plano free não exige checkout.",
    };
  }

  const successUrl =
    typeof window !== "undefined"
      ? `${window.location.origin}/billing/success?plan=${planId}&session_id={CHECKOUT_SESSION_ID}`
      : "/billing/success";
  const cancelUrl =
    typeof window !== "undefined"
      ? `${window.location.origin}/billing/cancel?plan=${planId}`
      : "/billing/cancel";

  if (!isBillingConfigured || !token) {
    throw new Error(
      "Billing não está configurado. Defina VITE_ENABLE_BILLING=true e endpoint de checkout.",
    );
  }

  const requestPayload: Record<string, string> = {
    plan_id: planId,
    success_url: successUrl,
    cancel_url: cancelUrl,
  };
  if (currentPassword) {
    requestPayload.current_password = currentPassword;
  }

  const response = await fetch(env.billingCheckoutEndpoint, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify(requestPayload),
  });

  const responseText = await response.text();
  let payload = null as {
    mode?: string;
    url?: string;
    checkout_url?: string;
    detail?: string;
    message?: string;
    error?: string;
  } | null;
  if (responseText) {
    try {
      payload = JSON.parse(responseText) as typeof payload;
    } catch {
      payload = null;
    }
  }

  const checkoutUrl = payload?.url || payload?.checkout_url;

  if (response.ok && (payload?.mode === "subscription_updated" || payload?.mode === "already_active")) {
    return {
      mode: "updated",
      url: "/billing",
      message: payload?.detail || "Subscription updated successfully.",
    };
  }

  if (!response.ok || !checkoutUrl) {
    const backendMessage =
      payload?.detail ||
      payload?.message ||
      payload?.error ||
      (responseText && responseText.length < 400 ? responseText : null);
    throw new Error(
      backendMessage ||
        `Billing checkout endpoint did not return a redirect URL (HTTP ${response.status})`,
    );
  }

  return {
    mode: "redirect",
    url: checkoutUrl,
  };
}

export async function startBillingPortal(token: string | null) {
  if (!isBillingConfigured || !token) {
    throw new Error(
      "Billing não está configurado. Defina VITE_ENABLE_BILLING=true e endpoint do portal.",
    );
  }

  const returnUrl =
    typeof window !== "undefined"
      ? `${window.location.origin}/billing`
      : "/billing";

  const response = await fetch(env.billingPortalEndpoint, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({
      return_url: returnUrl,
    }),
  });

  const payload = (await response.json().catch(() => null)) as {
    url?: string;
    detail?: string;
  } | null;
  if (!response.ok || !payload?.url) {
    throw new Error(
      payload?.detail || "Billing portal endpoint did not return a URL",
    );
  }

  return payload.url;
}

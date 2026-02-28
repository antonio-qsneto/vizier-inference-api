import { env, isBillingConfigured } from "@/env";
import type { UserProfile } from "@/types/api";

export interface BillingPlan {
  id: "free" | "professional" | "clinical";
  label: string;
  priceLabel: string;
  summary: string;
  features: string[];
}

export interface BillingCheckoutResult {
  mode: "redirect" | "mock";
  url: string;
  message?: string;
}

export const billingPlans: BillingPlan[] = [
  {
    id: "free",
    label: "Free",
    priceLabel: "US$ 0",
    summary: "Individual use and validation of inference flows.",
    features: ["1 seat", "Manual uploads", "Study monitoring"],
  },
  {
    id: "professional",
    label: "Profissional",
    priceLabel: "US$ 249",
    summary: "Small clinic workflow with invite and review operations.",
    features: ["5 seats", "Clinic onboarding", "Shared study history"],
  },
  {
    id: "clinical",
    label: "Clinical",
    priceLabel: "US$ 599",
    summary: "Higher throughput deployment for multi-radiologist teams.",
    features: ["10+ seats", "Advanced triage", "Priority support"],
  },
];

interface CheckoutInput {
  planId: BillingPlan["id"];
  token: string | null;
  user: UserProfile | null;
}

export async function startBillingCheckout({
  planId,
  token,
}: CheckoutInput): Promise<BillingCheckoutResult> {
  const successUrl =
    typeof window !== "undefined"
      ? `${window.location.origin}/billing/success?plan=${planId}`
      : "/billing/success";
  const cancelUrl =
    typeof window !== "undefined"
      ? `${window.location.origin}/billing/cancel?plan=${planId}`
      : "/billing/cancel";

  if (!isBillingConfigured || !token) {
    return {
      mode: "mock",
      url: successUrl,
      message:
        "Billing backend is not available in this repository. Replace the mock adapter with a Stripe checkout endpoint.",
    };
  }

  const response = await fetch(env.billingCheckoutEndpoint, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({
      plan_id: planId,
      success_url: successUrl,
      cancel_url: cancelUrl,
    }),
  });

  const payload = (await response.json().catch(() => null)) as
    | { url?: string; checkout_url?: string; detail?: string }
    | null;

  const checkoutUrl = payload?.url || payload?.checkout_url;

  if (!response.ok || !checkoutUrl) {
    throw new Error(
      payload?.detail || "Billing checkout endpoint did not return a redirect URL",
    );
  }

  return {
    mode: "redirect",
    url: checkoutUrl,
  };
}

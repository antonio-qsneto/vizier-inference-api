import {
  cancelClinicSubscription,
  syncClinicBilling,
  startClinicBillingCheckout,
  startClinicBillingPortal,
} from "@/api/services";
import type {
  ClinicBillingCheckoutResponse,
} from "@/types/api";

export type ClinicPlanId = "clinic_monthly" | "clinic_yearly";

const MONTHLY_SEAT_BRL = 679;
const YEARLY_SEAT_BRL = 7333;

export function getClinicSeatPrice(planId: ClinicPlanId) {
  return planId === "clinic_yearly" ? YEARLY_SEAT_BRL : MONTHLY_SEAT_BRL;
}

export function calculateClinicTotalPrice(planId: ClinicPlanId, seats: number) {
  const normalizedSeats = Number.isFinite(seats) ? Math.max(1, Math.floor(seats)) : 1;
  return getClinicSeatPrice(planId) * normalizedSeats;
}

export function formatBrlCurrency(amount: number) {
  return new Intl.NumberFormat("pt-BR", {
    style: "currency",
    currency: "BRL",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(amount);
}

export async function checkoutClinicPlan(params: {
  token: string;
  planId: ClinicPlanId;
  quantity?: number;
  successUrl?: string;
  cancelUrl?: string;
  clinicName?: string;
  cnpj?: string;
}) {
  const payload = await startClinicBillingCheckout(params.token, {
    plan_id: params.planId,
    quantity: params.quantity,
    success_url: params.successUrl,
    cancel_url: params.cancelUrl,
    clinic_name: params.clinicName,
    cnpj: params.cnpj,
  });

  return normalizeClinicCheckoutResponse(payload);
}

export async function openClinicBillingPortal(token: string, returnUrl?: string) {
  const response = await startClinicBillingPortal(token, returnUrl);
  return response.url;
}

export async function syncClinicBillingState(token: string, checkoutSessionId?: string) {
  return syncClinicBilling(token, checkoutSessionId);
}

export async function requestClinicDowngradeToIndividual(token: string) {
  return cancelClinicSubscription(token);
}

function normalizeClinicCheckoutResponse(
  payload: ClinicBillingCheckoutResponse,
): ClinicBillingCheckoutResponse {
  return {
    mode: payload.mode,
    detail: payload.detail,
    checkout_url: payload.checkout_url,
    checkout_session_id: payload.checkout_session_id,
    seat_limit: payload.seat_limit,
    seat_used: payload.seat_used,
  };
}

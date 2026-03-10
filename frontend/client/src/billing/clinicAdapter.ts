import {
  cancelClinicSubscription,
  changeClinicSeats,
  syncClinicBilling,
  startClinicBillingCheckout,
  startClinicBillingPortal,
} from "@/api/services";
import type {
  ClinicBillingCheckoutResponse,
  ClinicSeatChangeResponse,
} from "@/types/api";

export type ClinicPlanId = "clinic_monthly" | "clinic_yearly";

export const CLINIC_STRIPE_PRICE_IDS: Record<ClinicPlanId, string> = {
  clinic_monthly: "price_1T8SaSRVF2Q4eoQbLMeyYW3u",
  clinic_yearly: "price_1T8ScTRVF2Q4eoQbCpsCFqN1",
};

const MONTHLY_SEAT_BRL = 697;
const YEARLY_SEAT_BRL = 7527.6;

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
}) {
  const payload = await startClinicBillingCheckout(params.token, {
    plan_id: params.planId,
    quantity: params.quantity,
    success_url: params.successUrl,
    cancel_url: params.cancelUrl,
  });

  return normalizeClinicCheckoutResponse(payload);
}

export async function openClinicBillingPortal(token: string, returnUrl?: string) {
  const response = await startClinicBillingPortal(token, returnUrl);
  return response.url;
}

export async function updateClinicSeatQuantity(token: string, targetQuantity: number) {
  const response = await changeClinicSeats(token, targetQuantity);
  return normalizeSeatChangeResponse(response);
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

function normalizeSeatChangeResponse(
  payload: ClinicSeatChangeResponse,
): ClinicSeatChangeResponse {
  return {
    detail: payload.detail,
    seat_limit: payload.seat_limit,
    seat_used: payload.seat_used,
    scheduled_seat_limit: payload.scheduled_seat_limit,
    scheduled_seat_effective_at: payload.scheduled_seat_effective_at,
  };
}

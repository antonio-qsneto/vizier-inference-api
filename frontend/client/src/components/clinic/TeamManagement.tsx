import { FormEvent, useEffect, useMemo, useState } from "react";

import {
  calculateClinicTotalPrice,
  formatBrlCurrency,
} from "@/billing/clinicAdapter";
import { InlineNotice, Panel, StatusPill } from "@/components/primitives";
import type { Clinic, ClinicSubscriptionPlan, UserSummary } from "@/types/api";

import DoctorList from "./DoctorList";
import SeatSelector from "./SeatSelector";

interface TeamManagementProps {
  clinic: Clinic;
  doctors: UserSummary[];
  isAdmin: boolean;
  submitting?: boolean;
  openingPortal?: boolean;
  onInviteDoctor: (email: string) => Promise<void>;
  onRemoveDoctor: (doctorId: number) => Promise<void>;
  onChangeSeats: (targetQuantity: number) => Promise<void>;
  onOpenBillingPortal: () => Promise<void>;
}

function planLabel(plan: ClinicSubscriptionPlan | undefined) {
  if (plan === "clinic_yearly") {
    return "Clinic yearly";
  }
  if (plan === "clinic_monthly") {
    return "Clinic monthly";
  }
  return "Free";
}

export default function TeamManagement({
  clinic,
  doctors,
  isAdmin,
  submitting = false,
  openingPortal = false,
  onInviteDoctor,
  onRemoveDoctor,
  onChangeSeats,
  onOpenBillingPortal,
}: TeamManagementProps) {
  const [inviteEmail, setInviteEmail] = useState("");
  const [targetSeats, setTargetSeats] = useState(Math.max(1, clinic.seat_limit || 1));

  useEffect(() => {
    setTargetSeats(Math.max(1, clinic.seat_limit || 1));
  }, [clinic.seat_limit]);

  const seatsUsed = clinic.seat_used ?? clinic.active_doctors_count ?? doctors.length;
  const seatsLimit = Math.max(0, clinic.seat_limit || 0);
  const seatsProgress = useMemo(() => {
    if (seatsLimit <= 0) {
      return 0;
    }
    return Math.min(100, Math.round((seatsUsed / seatsLimit) * 100));
  }, [seatsLimit, seatsUsed]);

  const seatsReached = seatsLimit > 0 && seatsUsed >= seatsLimit;
  const canOpenBillingPortal =
    isAdmin &&
    clinic.subscription_plan !== "free" &&
    clinic.account_status !== "canceled";
  const expectedTotal =
    clinic.subscription_plan === "clinic_yearly" || clinic.subscription_plan === "clinic_monthly"
      ? calculateClinicTotalPrice(clinic.subscription_plan, targetSeats)
      : 0;

  async function handleInviteDoctor(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!inviteEmail.trim() || !isAdmin || seatsReached) {
      return;
    }
    await onInviteDoctor(inviteEmail.trim().toLowerCase());
    setInviteEmail("");
  }

  async function handleChangeSeats(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!isAdmin) {
      return;
    }
    await onChangeSeats(targetSeats);
  }

  return (
    <div className="space-y-6">
      <Panel className="space-y-5">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-400">
              Team management
            </p>
            <h2 className="mt-2 text-2xl font-semibold text-white">Clinic seats and doctors</h2>
            <p className="mt-2 text-sm leading-7 text-slate-300">
              Gerencie equipe médica, assentos comprados e cobrança Stripe da clínica.
            </p>
          </div>
          <StatusPill status={clinic.account_status || "unknown"} />
        </div>

        <div className="grid gap-4 sm:grid-cols-3">
          <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
            <p className="text-xs uppercase tracking-[0.18em] text-slate-400">Plan</p>
            <p className="mt-2 text-lg font-semibold text-white">{planLabel(clinic.subscription_plan)}</p>
          </div>
          <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
            <p className="text-xs uppercase tracking-[0.18em] text-slate-400">Seats used</p>
            <p className="mt-2 text-lg font-semibold text-white">
              {seatsUsed} / {seatsLimit}
            </p>
          </div>
          <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
            <p className="text-xs uppercase tracking-[0.18em] text-slate-400">Billing status</p>
            <p className="mt-2 text-lg font-semibold text-white">{clinic.account_status || "unknown"}</p>
          </div>
        </div>

        <div className="space-y-2">
          <div className="h-2 overflow-hidden rounded-full bg-white/10">
            <div
              className="h-full rounded-full bg-sky-400 transition-all"
              style={{ width: `${seatsProgress}%` }}
            />
          </div>
          <p className="text-xs uppercase tracking-[0.16em] text-slate-400">
            Seats used: {seatsProgress}%
          </p>
        </div>

        {clinic.has_pending_seat_reduction ? (
          <InlineNotice title="Seat reduction scheduled" tone="warning">
            Redução agendada para {clinic.scheduled_seat_limit} assentos em
            {" "}
            {clinic.scheduled_seat_effective_at
              ? new Date(clinic.scheduled_seat_effective_at).toLocaleString("pt-BR")
              : "próximo ciclo"}
            .
          </InlineNotice>
        ) : null}

        {seatsReached ? (
          <InlineNotice title="Seat limit reached" tone="warning">
            Não é possível convidar mais médicos até aumentar os assentos comprados.
          </InlineNotice>
        ) : null}

        <div className="flex flex-wrap gap-3">
          <button
            type="button"
            onClick={() => void onOpenBillingPortal()}
            disabled={!canOpenBillingPortal || openingPortal}
            className="rounded-2xl border border-white/10 bg-white/6 px-5 py-3 text-sm font-semibold text-slate-100 transition hover:bg-white/10 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {openingPortal
              ? "Abrindo Stripe..."
              : "Gerenciar/cancelar assinatura no Stripe"}
          </button>
        </div>

        {!canOpenBillingPortal ? (
          <p className="text-sm text-slate-400">
            Ative uma assinatura de clínica para liberar o portal Stripe.
          </p>
        ) : null}

      </Panel>

      {isAdmin ? (
        <Panel className="space-y-5">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-400">
              Invite doctor
            </p>
            <h3 className="mt-2 text-xl font-semibold text-white">Add a doctor seat</h3>
          </div>

          <form className="grid gap-4 md:grid-cols-[minmax(0,1fr)_auto]" onSubmit={handleInviteDoctor}>
            <input
              value={inviteEmail}
              onChange={(event) => setInviteEmail(event.target.value)}
              type="email"
              placeholder="doctor@clinic.com"
              disabled={submitting || seatsReached}
              className="rounded-2xl border border-white/10 bg-white/6 px-4 py-3 text-sm text-white outline-none placeholder:text-slate-500 focus:border-sky-300/50 disabled:cursor-not-allowed disabled:opacity-60"
            />
            <button
              type="submit"
              disabled={submitting || seatsReached || !inviteEmail.trim()}
              className="rounded-2xl bg-sky-500 px-5 py-3 text-sm font-semibold text-white transition hover:bg-sky-400 disabled:cursor-not-allowed disabled:opacity-60"
            >
              Invite Doctor
            </button>
          </form>
        </Panel>
      ) : null}

      {isAdmin ? (
        <Panel className="space-y-5">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-400">
              Change seats
            </p>
            <h3 className="mt-2 text-xl font-semibold text-white">Update purchased seats</h3>
          </div>

          <form className="space-y-4" onSubmit={handleChangeSeats}>
            <SeatSelector
              value={targetSeats}
              onChange={setTargetSeats}
              min={Math.max(1, seatsUsed)}
              disabled={submitting}
              description={`Mínimo atual: ${Math.max(1, seatsUsed)} médico(s)`}
            />

            {clinic.subscription_plan === "clinic_monthly" ||
            clinic.subscription_plan === "clinic_yearly" ? (
              <p className="text-sm text-slate-300">
                Estimativa para {targetSeats} assentos: {formatBrlCurrency(expectedTotal)} /
                {" "}
                {clinic.subscription_plan === "clinic_yearly" ? "ano" : "mês"}
              </p>
            ) : null}

            <button
              type="submit"
              disabled={submitting || targetSeats === seatsLimit}
              className="rounded-2xl border border-sky-300/30 bg-sky-500/10 px-5 py-3 text-sm font-semibold text-sky-100 transition hover:bg-sky-500/20 disabled:cursor-not-allowed disabled:opacity-60"
            >
              Change Seats
            </button>
          </form>
        </Panel>
      ) : null}

      <Panel className="space-y-4">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-400">
            Doctors
          </p>
          <h3 className="mt-2 text-xl font-semibold text-white">Current clinic team</h3>
        </div>

        <DoctorList
          doctors={doctors}
          isAdmin={isAdmin}
          disablingActions={submitting}
          onRemoveDoctor={onRemoveDoctor}
        />
      </Panel>
    </div>
  );
}

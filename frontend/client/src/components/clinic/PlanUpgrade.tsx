import { useEffect, useMemo, useState } from "react";

import {
  calculateClinicTotalPrice,
  CLINIC_STRIPE_PRICE_IDS,
  formatBrlCurrency,
  getClinicSeatPrice,
  type ClinicPlanId,
} from "@/billing/clinicAdapter";
import { InlineNotice, Panel } from "@/components/primitives";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import type { Clinic } from "@/types/api";

import SeatSelector from "./SeatSelector";

interface PlanUpgradePayload {
  clinicName: string;
  cnpj: string;
  seats: number;
  planId: ClinicPlanId;
}

interface PlanUpgradeProps {
  submitting?: boolean;
  onUpgrade: (payload: PlanUpgradePayload) => Promise<void>;
  existingClinic?: Clinic;
}

export default function PlanUpgrade({
  submitting = false,
  onUpgrade,
  existingClinic,
}: PlanUpgradeProps) {
  const [clinicName, setClinicName] = useState(existingClinic?.name || "");
  const [cnpj, setCnpj] = useState(existingClinic?.cnpj || "");
  const [planId, setPlanId] = useState<ClinicPlanId>("clinic_monthly");
  const [seats, setSeats] = useState(
    Math.max(1, existingClinic?.seat_used || existingClinic?.active_doctors_count || 1),
  );
  const [confirmOpen, setConfirmOpen] = useState(false);

  useEffect(() => {
    if (!existingClinic) {
      return;
    }
    setClinicName(existingClinic.name || "");
    setCnpj(existingClinic.cnpj || "");
    setSeats(Math.max(1, existingClinic.seat_used || existingClinic.active_doctors_count || 1));
  }, [existingClinic]);

  const seatPrice = useMemo(() => getClinicSeatPrice(planId), [planId]);
  const totalPrice = useMemo(
    () => calculateClinicTotalPrice(planId, seats),
    [planId, seats],
  );

  const cycleLabel = planId === "clinic_yearly" ? "ano" : "mês";
  const minimumSeats = Math.max(
    1,
    existingClinic?.seat_used || existingClinic?.active_doctors_count || 1,
  );

  async function handleConfirmUpgrade() {
    if (!clinicName.trim()) {
      return;
    }

    await onUpgrade({
      clinicName: clinicName.trim(),
      cnpj: cnpj.trim(),
      seats,
      planId,
    });
  }

  const isExistingClinic = Boolean(existingClinic);
  return (
    <>
      <Panel className="space-y-5">
        <div className="space-y-2">
          <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-400">
            Upgrade de plano
          </p>
          <h2 className="text-2xl font-semibold text-white">
            {isExistingClinic
              ? "Ativar assinatura da clínica"
              : "Ativar plano de clínica (por assento)"}
          </h2>
          <p className="text-sm leading-7 text-slate-300">
            {isExistingClinic ? (
              <>Escolha ciclo e assentos para iniciar a cobrança Stripe da sua clínica.</>
            ) : (
              <>
                Ao ativar, seu usuário será convertido de <strong>Individual</strong> para{" "}
                <strong>Administrador da clínica</strong>. Assinaturas de clínica são cobradas por médico.
              </>
            )}
          </p>
        </div>

        <InlineNotice title={isExistingClinic ? "Ativação da assinatura" : "Conversão de conta"}>
          {isExistingClinic ? (
            <>
              A clínica já foi criada. Agora finalize no Stripe para liberar recursos pagos
              (incluindo upload).
            </>
          ) : (
            <>
              O upgrade cria uma conta de clínica, define você como administrador e inicia o pagamento
              Stripe com quantidade de assentos igual ao número de médicos planejado.
            </>
          )}
        </InlineNotice>

        <div className="grid gap-4">
          <input
            value={clinicName}
            onChange={(event) => setClinicName(event.target.value)}
            placeholder="Nome da clínica"
            disabled={isExistingClinic}
            className="rounded-2xl border border-white/10 bg-white/6 px-4 py-3 text-sm text-white outline-none placeholder:text-slate-500 focus:border-sky-300/50"
          />
          <input
            value={cnpj}
            onChange={(event) => setCnpj(event.target.value)}
            placeholder="CNPJ (opcional)"
            disabled={isExistingClinic}
            className="rounded-2xl border border-white/10 bg-white/6 px-4 py-3 text-sm text-white outline-none placeholder:text-slate-500 focus:border-sky-300/50"
          />

          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">
                Ciclo de cobrança
              </p>
              <select
                value={planId}
                onChange={(event) => setPlanId(event.target.value as ClinicPlanId)}
                className="h-10 w-full rounded-xl border border-white/12 bg-white/6 px-3 text-sm font-semibold text-white outline-none transition focus:border-sky-300/50"
              >
                <option value="clinic_monthly" className="bg-slate-900">
                  Mensal
                </option>
                <option value="clinic_yearly" className="bg-slate-900">
                  Anual (10% de desconto)
                </option>
              </select>
            </div>

            <SeatSelector
              value={seats}
              onChange={setSeats}
              min={minimumSeats}
              label="Assentos de médicos"
              description={
                isExistingClinic
                  ? `Mínimo atual: ${minimumSeats} médico(s)`
                  : "Quantidade inicial de médicos"
              }
            />
          </div>

          <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <p className="text-sm text-slate-300">
                {formatBrlCurrency(seatPrice)} por assento / {cycleLabel}
              </p>
              <p className="text-xl font-semibold text-white">
                Total: {formatBrlCurrency(totalPrice)} / {cycleLabel}
              </p>
            </div>
            <p className="mt-2 text-xs uppercase tracking-[0.16em] text-slate-500">
              ID de preço Stripe: {CLINIC_STRIPE_PRICE_IDS[planId]}
            </p>
          </div>
        </div>

        <button
          type="button"
          onClick={() => setConfirmOpen(true)}
          disabled={!clinicName.trim() || submitting}
          className="rounded-2xl bg-sky-500 px-5 py-3 text-sm font-semibold text-white transition hover:bg-sky-400 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {submitting
            ? "Iniciando pagamento..."
            : isExistingClinic
              ? "Ativar assinatura no Stripe"
              : "Ativar plano de clínica"}
        </button>
      </Panel>

      <Dialog open={confirmOpen} onOpenChange={setConfirmOpen}>
        <DialogContent className="border-white/12 bg-[#191b20] text-white">
          <DialogHeader>
            <DialogTitle>Confirmar upgrade para clínica</DialogTitle>
            <DialogDescription className="text-slate-300">
              {isExistingClinic ? (
                <>
                  Você irá iniciar/ajustar a assinatura Stripe da clínica{" "}
                  <strong>{clinicName || "sua clínica"}</strong>.
                </>
              ) : (
                <>
                  Você será promovido para <strong>Administrador da clínica</strong> de "{clinicName || "sua clínica"}".
                </>
              )}{" "}
              Assentos iniciais: <strong>{seats}</strong>.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-2 rounded-xl border border-white/12 bg-white/6 px-4 py-3 text-sm text-slate-200">
            <p>
              Plano: <strong>{planId === "clinic_yearly" ? "Anual" : "Mensal"}</strong>
            </p>
            <p>
              Valor total: <strong>{formatBrlCurrency(totalPrice)} / {cycleLabel}</strong>
            </p>
            {planId === "clinic_yearly" ? (
              <p className="text-emerald-200">Inclui desconto de 10% no ciclo anual.</p>
            ) : null}
          </div>

          <DialogFooter>
            <button
              type="button"
              onClick={() => setConfirmOpen(false)}
              disabled={submitting}
              className="rounded-xl border border-white/10 bg-white/6 px-4 py-2 text-sm font-semibold text-slate-200 transition hover:bg-white/10 disabled:cursor-not-allowed disabled:opacity-60"
            >
              Cancelar
            </button>
            <button
              type="button"
              onClick={() => void handleConfirmUpgrade()}
              disabled={submitting || !clinicName.trim()}
              className="rounded-xl bg-sky-500 px-4 py-2 text-sm font-semibold text-white transition hover:bg-sky-400 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {submitting ? "Processando..." : "Confirmar e abrir Stripe"}
            </button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}

import { useCallback, useEffect, useRef, useState } from "react";
import { motion } from "framer-motion";
import { toast } from "sonner";

import { ApiError } from "@/api/client";
import {
  cancelInvitation,
  fetchClinicBillingPlans,
  fetchClinicInvitations,
  fetchClinicTeamMembers,
  fetchClinics,
  fetchMyInvitations,
  getPageResults,
  inviteDoctor,
  leaveClinic,
  removeDoctor,
} from "@/api/services";
import { useAuth } from "@/auth/AuthContext";
import {
  checkoutClinicPlan,
  openClinicBillingPortal,
  syncClinicBillingState,
  type ClinicPlanId,
} from "@/billing/clinicAdapter";
import PlanUpgrade from "@/components/clinic/PlanUpgrade";
import TeamManagement from "@/components/clinic/TeamManagement";
import {
  EmptyState,
  InlineNotice,
  LoadingState,
  PageIntro,
  Panel,
  StatusPill,
} from "@/components/primitives";
import { formatDateTime } from "@/lib/format";
import type { Clinic, DoctorInvitation, UserSummary } from "@/types/api";

const BILLING_SYNC_ATTEMPTS = 8;
const BILLING_SYNC_DELAY_MS = 1500;

function wait(ms: number) {
  return new Promise((resolve) => {
    setTimeout(resolve, ms);
  });
}

export default function ClinicPage() {
  const { accessToken, refreshProfile, user } = useAuth();
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [openingPortal, setOpeningPortal] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [clinic, setClinic] = useState<Clinic | null>(null);
  const [doctors, setDoctors] = useState<UserSummary[]>([]);
  const [clinicInvitations, setClinicInvitations] = useState<DoctorInvitation[]>([]);
  const [myInvitations, setMyInvitations] = useState<DoctorInvitation[]>([]);
  const [billingEnabled, setBillingEnabled] = useState(true);
  const billingReturnHandledRef = useRef(false);

  const effectiveRole =
    user?.effective_role ||
    (user?.role === "CLINIC_ADMIN"
      ? "clinic_admin"
      : user?.role === "CLINIC_DOCTOR"
        ? "clinic_doctor"
        : "individual");
  const isClinicAdmin = effectiveRole === "clinic_admin";
  const isClinicDoctor = effectiveRole === "clinic_doctor" && Boolean(user?.clinic_id);

  const loadClinicData = useCallback(async () => {
    if (!accessToken) {
      return;
    }

    setLoading(true);
    try {
      const clinicsResponse = await fetchClinics(accessToken);
      const nextClinic = getPageResults<Clinic>(clinicsResponse)[0] ?? null;

      const myInvitesPromise = fetchMyInvitations(accessToken);
      const adminOnlyPromises =
        nextClinic && isClinicAdmin
          ? Promise.all([
              fetchClinicInvitations(accessToken).then((payload) =>
                getPageResults<DoctorInvitation>(payload),
              ),
              fetchClinicTeamMembers(accessToken),
              fetchClinicBillingPlans(accessToken),
            ])
          : Promise.resolve<[DoctorInvitation[], null, null]>([[], null, null]);

      const [nextMyInvitationsRaw, [nextClinicInvitations, teamMembers, billingCatalog]] =
        await Promise.all([myInvitesPromise, adminOnlyPromises]);
      const nextMyInvitations =
        getPageResults<DoctorInvitation>(nextMyInvitationsRaw);

      let mergedClinic = nextClinic;
      if (nextClinic && teamMembers) {
        mergedClinic = {
          ...nextClinic,
          seat_limit: teamMembers.seat_limit,
          seat_used: teamMembers.seats_used,
          account_status: teamMembers.account_status,
        };
      }

      if (nextClinic && billingCatalog) {
        mergedClinic = {
          ...mergedClinic,
          seat_limit: billingCatalog.seat_limit,
          seat_used: billingCatalog.seat_used,
          account_status: billingCatalog.account_status,
          subscription_plan: billingCatalog.current_plan,
        };
        setBillingEnabled(billingCatalog.billing_enabled);
      } else {
        setBillingEnabled(true);
      }

      setClinic(mergedClinic);
      setDoctors(teamMembers?.doctors || []);
      setClinicInvitations(nextClinicInvitations || []);
      setMyInvitations(nextMyInvitations);
      setError(null);
    } catch (requestError) {
      if (requestError instanceof Error) {
        setError(requestError.message);
      }
    } finally {
      setLoading(false);
    }
  }, [accessToken, isClinicAdmin]);

  useEffect(() => {
    void loadClinicData();
  }, [loadClinicData]);

  useEffect(() => {
    if (billingReturnHandledRef.current) {
      return;
    }

    const query = new URLSearchParams(window.location.search);
    const billingStatus = query.get("billing");
    if (billingStatus === "cancel") {
      toast.message("Pagamento Stripe cancelado.");
      billingReturnHandledRef.current = true;
      return;
    }
    if (billingStatus !== "success") {
      return;
    }

    billingReturnHandledRef.current = true;
    toast.success("Pagamento Stripe concluído.");

    if (
      !accessToken ||
      !(isClinicAdmin || (effectiveRole === "individual" && !user?.clinic_id))
    ) {
      return;
    }

    const token = accessToken;
    const checkoutSessionId = query.get("session_id") || undefined;
    let cancelled = false;

    async function syncBillingFromCheckoutReturn() {
      for (let attempt = 0; attempt < BILLING_SYNC_ATTEMPTS; attempt += 1) {
        try {
          await syncClinicBillingState(token, checkoutSessionId);
          if (!cancelled) {
            await refreshProfile();
            await loadClinicData();
          }
          return;
        } catch (requestError) {
          const shouldRetry =
            requestError instanceof ApiError &&
            requestError.status === 409 &&
            attempt < BILLING_SYNC_ATTEMPTS - 1;
          if (shouldRetry) {
            await wait(BILLING_SYNC_DELAY_MS);
            continue;
          }

          if (!cancelled) {
            toast.error(
              requestError instanceof Error
                ? requestError.message
                : "Falha ao sincronizar assinatura após pagamento",
            );
            await loadClinicData();
          }
          return;
        }
      }
    }

    void syncBillingFromCheckoutReturn();
    return () => {
      cancelled = true;
    };
  }, [accessToken, effectiveRole, isClinicAdmin, loadClinicData, refreshProfile, user?.clinic_id]);

  async function startClinicCheckout(
    token: string,
    planId: ClinicPlanId,
    seats: number,
    options?: {
      clinicName?: string;
      cnpj?: string;
    },
  ) {
    const successUrl = `${window.location.origin}/clinic?billing=success&session_id={CHECKOUT_SESSION_ID}`;
    const cancelUrl = `${window.location.origin}/clinic?billing=cancel`;

    const checkoutResponse = await checkoutClinicPlan({
      token,
      planId,
      quantity: seats,
      successUrl,
      cancelUrl,
      clinicName: options?.clinicName,
      cnpj: options?.cnpj,
    });

    if (checkoutResponse.checkout_url) {
      window.location.assign(checkoutResponse.checkout_url);
      return;
    }

    toast.success(checkoutResponse.detail || "Plano de clínica atualizado.");
    await refreshProfile();
    await loadClinicData();
  }

  async function handleUpgradeToClinic(payload: {
    clinicName: string;
    cnpj: string;
    seats: number;
    planId: ClinicPlanId;
  }) {
    if (!accessToken) {
      return;
    }

    setSubmitting(true);
    try {
      await startClinicCheckout(accessToken, payload.planId, payload.seats, {
        clinicName: payload.clinicName,
        cnpj: payload.cnpj,
      });
    } catch (requestError) {
      toast.error(
        requestError instanceof Error
          ? requestError.message
          : "Falha ao ativar plano de clínica",
      );
      throw requestError;
    } finally {
      setSubmitting(false);
    }
  }

  async function handleActivateExistingClinicPlan(payload: {
    clinicName: string;
    cnpj: string;
    seats: number;
    planId: ClinicPlanId;
  }) {
    if (!accessToken) {
      return;
    }

    setSubmitting(true);
    try {
      await startClinicCheckout(accessToken, payload.planId, payload.seats);
    } catch (requestError) {
      toast.error(
        requestError instanceof Error ? requestError.message : "Falha ao iniciar pagamento da clínica",
      );
      throw requestError;
    } finally {
      setSubmitting(false);
    }
  }

  async function handleInviteDoctor(email: string) {
    if (!accessToken) {
      return;
    }

    if (
      clinic &&
      (clinic.seat_limit ?? 0) > 0 &&
      (clinic.seat_used ?? 0) >= (clinic.seat_limit ?? 0)
    ) {
      toast.error("Limite de assentos atingido para esta clínica.");
      return;
    }

    setSubmitting(true);
    try {
      await inviteDoctor(accessToken, email);
      toast.success("Convite enviado");
      await loadClinicData();
    } catch (requestError) {
      toast.error(
        requestError instanceof Error ? requestError.message : "Falha ao enviar convite",
      );
    } finally {
      setSubmitting(false);
    }
  }

  async function handleRemoveDoctor(doctorId: number) {
    if (!accessToken) {
      return;
    }

    setSubmitting(true);
    try {
      await removeDoctor(accessToken, doctorId);
      toast.success("Médico removido");
      await loadClinicData();
    } catch (requestError) {
      toast.error(
        requestError instanceof Error ? requestError.message : "Falha ao remover médico",
      );
    } finally {
      setSubmitting(false);
    }
  }

  async function handleOpenBillingPortal() {
    if (!accessToken) {
      return;
    }

    setOpeningPortal(true);
    try {
      const portalUrl = await openClinicBillingPortal(
        accessToken,
        `${window.location.origin}/clinic`,
      );
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

  async function handleCancelInvitation(invitationId: string) {
    if (!accessToken) {
      return;
    }

    setSubmitting(true);
    try {
      await cancelInvitation(accessToken, invitationId);
      toast.success("Convite cancelado");
      await loadClinicData();
    } catch (requestError) {
      toast.error(
        requestError instanceof Error ? requestError.message : "Falha ao cancelar convite",
      );
    } finally {
      setSubmitting(false);
    }
  }

  async function handleLeaveClinic() {
    if (!accessToken) {
      return;
    }

    const confirmed = window.confirm(
      "Você será desvinculado desta clínica e voltará para o plano individual gratuito. Deseja continuar?",
    );
    if (!confirmed) {
      return;
    }

    setSubmitting(true);
    try {
      const response = await leaveClinic(accessToken);
      toast.success(response.detail);
      await refreshProfile();
      await loadClinicData();
    } catch (requestError) {
      toast.error(
        requestError instanceof Error
          ? requestError.message
          : "Falha ao desvincular da clínica",
      );
    } finally {
      setSubmitting(false);
    }
  }

  const hasClinicMembership = Boolean(clinic && user?.clinic_id);
  const isClinicPlanAccount = Boolean(
    clinic && (clinic.plan_type === "clinic" || hasClinicMembership),
  );
  const isIndividualUserWithoutClinic = Boolean(
    effectiveRole === "individual" && !user?.clinic_id,
  );
  const isIndividualPaidSubscriber = Boolean(
    isIndividualUserWithoutClinic &&
      user?.subscription_plan &&
      user.subscription_plan !== "free",
  );
  const canShowIndividualUpgrade = Boolean(
    (isIndividualUserWithoutClinic && !isIndividualPaidSubscriber) ||
      clinic?.plan_type === "individual",
  );

  if (loading) {
    return <LoadingState label="Carregando dados da clínica..." />;
  }

  return (
    <motion.section
      initial={{ opacity: 0, y: 18 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35 }}
      className="space-y-6"
    >
      <PageIntro
        eyebrow="Clínica"
        title="Plano da clínica e gestão da equipe"
        description="Fluxo de upgrade de usuário individual para administrador da clínica, com assentos por médico, cobrança Stripe e gestão da equipe."
      />

      {error ? <InlineNotice title="Erro no fluxo da clínica">{error}</InlineNotice> : null}

      {!billingEnabled ? (
        <InlineNotice title="Assinatura desabilitada" tone="warning">
          O modo de assinatura Stripe está desativado no ambiente atual.
        </InlineNotice>
      ) : null}

      {isClinicPlanAccount && clinic ? (
        isClinicAdmin ? (
          <div className="grid gap-6 xl:grid-cols-[0.85fr_1.15fr]">
            <Panel className="space-y-5">
              <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-400">
                Perfil da clínica
              </p>
              <h2 className="text-3xl font-semibold text-white">{clinic.name}</h2>

              <div className="grid gap-4 sm:grid-cols-2">
                <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
                  <p className="text-xs uppercase tracking-[0.18em] text-slate-400">Plano</p>
                  <p className="mt-2 text-lg font-semibold text-white">{clinic.subscription_plan}</p>
                </div>
                <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
                  <p className="text-xs uppercase tracking-[0.18em] text-slate-400">Assentos</p>
                  <p className="mt-2 text-lg font-semibold text-white">
                    {clinic.seat_used ?? 0} / {clinic.seat_limit ?? 0}
                  </p>
                </div>
              </div>

              <div className="flex flex-wrap gap-2">
                <StatusPill status={clinic.account_status || "unknown"} />
                <StatusPill status={clinic.plan_type || "unknown"} />
              </div>

              <p className="text-sm leading-7 text-slate-300">
                Responsável: {clinic.owner?.email || "N/D"} · Criada em{" "}
                {clinic.created_at ? formatDateTime(clinic.created_at) : "N/D"}
              </p>
            </Panel>

            <TeamManagement
              clinic={clinic}
              doctors={doctors}
              isAdmin={true}
              submitting={submitting}
              openingPortal={openingPortal}
              onInviteDoctor={handleInviteDoctor}
              onRemoveDoctor={handleRemoveDoctor}
              onOpenBillingPortal={handleOpenBillingPortal}
            />

            {clinic.subscription_plan === "free" ? (
              <div className="xl:col-span-2">
                <PlanUpgrade
                  submitting={submitting}
                  onUpgrade={handleActivateExistingClinicPlan}
                  existingClinic={clinic}
                />
              </div>
            ) : null}

            <Panel className="space-y-4 xl:col-span-2">
              <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-400">
                Histórico de convites
              </p>
              <div className="space-y-3">
                {clinicInvitations.length ? (
                  clinicInvitations.map((invitation) => (
                    <div
                      key={invitation.id}
                      className="rounded-3xl border border-white/10 bg-white/5 px-4 py-4"
                    >
                      <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
                        <div>
                          <div className="flex flex-wrap items-center gap-3">
                            <StatusPill status={invitation.status} />
                            <p className="text-sm font-semibold text-white">{invitation.email}</p>
                          </div>
                          <p className="mt-3 text-sm text-slate-300">
                            Convidado por {invitation.invited_by_email}
                          </p>
                          <p className="mt-1 text-xs uppercase tracking-[0.18em] text-slate-500">
                            Expira em {formatDateTime(invitation.expires_at)}
                          </p>
                        </div>
                        {invitation.status === "PENDING" ? (
                          <button
                            type="button"
                            onClick={() => void handleCancelInvitation(invitation.id)}
                            disabled={submitting}
                            className="rounded-full border border-rose-300/25 bg-rose-500/10 px-4 py-2 text-sm font-semibold text-rose-100 transition hover:bg-rose-500/20 disabled:cursor-not-allowed disabled:opacity-60"
                          >
                            Cancelar convite
                          </button>
                        ) : null}
                      </div>
                    </div>
                  ))
                ) : (
                  <p className="text-sm leading-7 text-slate-300">
                    Nenhum convite encontrado para esta clínica.
                  </p>
                )}
              </div>
            </Panel>
          </div>
        ) : isClinicDoctor ? (
          <Panel className="space-y-5">
            <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-400">
              Vínculo com clínica
            </p>
            <h2 className="text-3xl font-semibold text-white">{clinic.name}</h2>
            <InlineNotice title="Acesso de médico vinculado">
              Você está vinculado a esta clínica como médico. Dados de assinatura e
              gestão de assentos ficam visíveis apenas para administradores.
            </InlineNotice>
            <button
              type="button"
              onClick={() => void handleLeaveClinic()}
              disabled={submitting}
              className="rounded-2xl border border-amber-300/30 bg-amber-500/10 px-5 py-3 text-sm font-semibold text-amber-100 transition hover:bg-amber-500/20 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {submitting ? "Desvinculando..." : "Desvincular da clínica"}
            </button>
          </Panel>
        ) : (
          <EmptyState
            title="Vínculo com clínica"
            description="Este perfil não possui permissão para gerenciar esta clínica."
          />
        )
      ) : canShowIndividualUpgrade ? (
        <div className="grid gap-6 xl:grid-cols-[1.05fr_0.95fr]">
          <PlanUpgrade
            submitting={submitting}
            onUpgrade={clinic ? handleActivateExistingClinicPlan : handleUpgradeToClinic}
            existingClinic={clinic || undefined}
          />

          {myInvitations.length ? (
            <Panel className="space-y-4">
              <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-400">
                Convites pendentes
              </p>
              {myInvitations.map((invitation) => (
                <div
                  key={invitation.id}
                  className="rounded-3xl border border-white/10 bg-white/5 px-4 py-4"
                >
                  <div className="flex flex-wrap items-center gap-3">
                    <StatusPill status={invitation.status} />
                    <p className="text-sm font-semibold text-white">{invitation.clinic_name}</p>
                  </div>
                  <p className="mt-3 text-sm leading-7 text-slate-300">
                    Enviado por {invitation.invited_by_email}. Aceite o convite para entrar na clínica.
                  </p>
                </div>
              ))}
            </Panel>
          ) : (
            <EmptyState
              title="Nenhuma clínica vinculada ainda"
              description="Ative um plano de clínica para criar sua clínica ou aguarde um convite."
            />
          )}
        </div>
      ) : isIndividualPaidSubscriber ? (
        <InlineNotice title="Migração para clínica indisponível">
          Assinantes individuais com plano ativo não podem virar administrador de clínica.
          Cancele o plano individual e aguarde o fim do ciclo para criar clínica.
        </InlineNotice>
      ) : (
        <EmptyState
          title="Plano de clínica indisponível"
          description="Apenas usuários individuais podem iniciar o upgrade para o plano de clínica neste fluxo."
        />
      )}
    </motion.section>
  );
}

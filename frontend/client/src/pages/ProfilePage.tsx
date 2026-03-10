import { useCallback, useEffect, useMemo, useState } from "react";
import { useLocation } from "wouter";
import { toast } from "sonner";

import {
  cancelClinicSubscription,
  cancelIndividualBilling,
  deleteAccount,
  fetchOffboardingStatus,
} from "@/api/services";
import { useAuth } from "@/auth/AuthContext";
import { InlineNotice, LoadingState, PageIntro, Panel } from "@/components/primitives";
import { formatDateTime } from "@/lib/format";
import type { OffboardingStatus } from "@/types/api";

export default function ProfilePage() {
  const [, navigate] = useLocation();
  const { accessToken, logout, refreshProfile, user } = useAuth();

  const [loading, setLoading] = useState(true);
  const [submittingCancel, setSubmittingCancel] = useState(false);
  const [submittingDelete, setSubmittingDelete] = useState(false);
  const [statusPayload, setStatusPayload] = useState<OffboardingStatus | null>(null);
  const [confirmText, setConfirmText] = useState("");
  const [currentPassword, setCurrentPassword] = useState("");

  const effectiveRole = useMemo(() => {
    if (user?.effective_role) {
      return user.effective_role;
    }
    if (user?.role === "CLINIC_ADMIN") {
      return "clinic_admin";
    }
    if (user?.role === "CLINIC_DOCTOR") {
      return "clinic_doctor";
    }
    return "individual";
  }, [user?.effective_role, user?.role]);

  const loadStatus = useCallback(async () => {
    if (!accessToken) {
      return;
    }
    setLoading(true);
    try {
      const payload = await fetchOffboardingStatus(accessToken);
      setStatusPayload(payload);
    } catch (requestError) {
      toast.error(
        requestError instanceof Error
          ? requestError.message
          : "Falha ao carregar estado de offboarding",
      );
    } finally {
      setLoading(false);
    }
  }, [accessToken]);

  useEffect(() => {
    void loadStatus();
  }, [loadStatus]);

  async function handleCancelSubscription() {
    if (!accessToken || !statusPayload?.can_cancel_subscription) {
      return;
    }

    setSubmittingCancel(true);
    try {
      if (statusPayload.subscription_scope === "individual") {
        const result = await cancelIndividualBilling(accessToken);
        toast.success(result.detail);
      } else if (
        statusPayload.subscription_scope === "clinic" &&
        effectiveRole === "clinic_admin"
      ) {
        const result = await cancelClinicSubscription(accessToken);
        toast.success(result.detail);
      } else {
        toast.error("Este perfil não pode cancelar assinatura neste escopo.");
        return;
      }

      await refreshProfile();
      await loadStatus();
    } catch (requestError) {
      toast.error(
        requestError instanceof Error ? requestError.message : "Falha ao cancelar assinatura",
      );
    } finally {
      setSubmittingCancel(false);
    }
  }

  async function handleDeleteAccount() {
    if (!accessToken) {
      return;
    }

    setSubmittingDelete(true);
    try {
      const response = await deleteAccount(accessToken, {
        confirm_text: confirmText,
        current_password: currentPassword || undefined,
      });
      toast.success(response.detail);
      logout(false);
      navigate("/login");
    } catch (requestError) {
      toast.error(
        requestError instanceof Error ? requestError.message : "Falha ao excluir conta",
      );
      await loadStatus();
    } finally {
      setSubmittingDelete(false);
    }
  }

  if (loading) {
    return <LoadingState label="Carregando dados de perfil..." />;
  }

  return (
    <section className="space-y-6">
      <PageIntro
        eyebrow="Perfil"
        title="Gerenciar perfil e offboarding"
        description="Cancelamento de assinatura e exclusão de conta com validações de billing."
      />

      <Panel className="space-y-4">
        <p className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-400">
          Conta
        </p>
        <p className="text-lg font-semibold text-white">{user?.full_name || user?.email}</p>
        <p className="text-sm text-slate-300">Email: {user?.email}</p>
        <p className="text-sm text-slate-300">
          Role efetiva: {statusPayload?.effective_role || effectiveRole}
        </p>
        <p className="text-sm text-slate-300">
          Estado da conta: {user?.account_lifecycle_status || "active"}
        </p>
      </Panel>

      <Panel className="space-y-4">
        <p className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-400">
          Assinatura
        </p>
        <p className="text-sm text-slate-300">
          Escopo: {statusPayload?.subscription_scope || "none"} · Status:{" "}
          {statusPayload?.status || "none"}
        </p>
        {statusPayload?.billing_period_end ? (
          <InlineNotice title="Acesso até o fim do ciclo">
            Assinatura cancelada. O acesso permanece até{" "}
            {formatDateTime(statusPayload.billing_period_end)}.
          </InlineNotice>
        ) : null}

        <button
          type="button"
          onClick={() => void handleCancelSubscription()}
          disabled={!statusPayload?.can_cancel_subscription || submittingCancel}
          className="rounded-2xl border border-white/10 bg-white/6 px-5 py-3 text-sm font-semibold text-slate-100 transition hover:bg-white/10 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {submittingCancel ? "Cancelando..." : "Cancelar assinatura"}
        </button>
      </Panel>

      <Panel className="space-y-4 border-rose-300/25 bg-rose-500/5">
        <p className="text-xs font-semibold uppercase tracking-[0.2em] text-rose-200">
          Danger Zone
        </p>
        {statusPayload?.blockers?.length ? (
          <div className="space-y-2 rounded-xl border border-amber-300/30 bg-amber-500/10 p-3 text-sm text-amber-50">
            {statusPayload.blockers.map((blocker) => (
              <p key={blocker.code}>
                {blocker.code}: {blocker.message}
              </p>
            ))}
          </div>
        ) : (
          <p className="text-sm text-slate-300">
            Sem bloqueios ativos. Você pode seguir com a exclusão da conta.
          </p>
        )}

        <div className="grid gap-3 md:grid-cols-2">
          <input
            type="text"
            value={confirmText}
            onChange={(event) => setConfirmText(event.target.value)}
            placeholder='Digite "EXCLUIR" para confirmar'
            className="rounded-xl border border-white/15 bg-[#21232a] px-3 py-2 text-sm text-white outline-none transition focus:border-rose-300/70"
          />
          <input
            type="password"
            value={currentPassword}
            onChange={(event) => setCurrentPassword(event.target.value)}
            placeholder="Senha atual (quando aplicável)"
            className="rounded-xl border border-white/15 bg-[#21232a] px-3 py-2 text-sm text-white outline-none transition focus:border-rose-300/70"
          />
        </div>

        <button
          type="button"
          onClick={() => void handleDeleteAccount()}
          disabled={!statusPayload?.can_delete_account || submittingDelete}
          className="rounded-2xl border border-rose-300/40 bg-rose-500/20 px-5 py-3 text-sm font-semibold text-rose-100 transition hover:bg-rose-500/30 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {submittingDelete ? "Excluindo..." : "Excluir conta"}
        </button>
      </Panel>
    </section>
  );
}

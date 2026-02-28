import { useCallback, useEffect, useState } from "react";
import { motion } from "framer-motion";
import { toast } from "sonner";
import { acceptInvitation, fetchMyInvitations } from "@/api/services";
import { useAuth } from "@/auth/AuthContext";
import {
  EmptyState,
  LoadingState,
  PageIntro,
  Panel,
  StatusPill,
} from "@/components/primitives";
import { formatDateTime } from "@/lib/format";
import type { DoctorInvitation } from "@/types/api";

export default function InvitationsPage() {
  const { accessToken, refreshProfile } = useAuth();
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [invitations, setInvitations] = useState<DoctorInvitation[]>([]);
  const [error, setError] = useState<string | null>(null);

  const loadInvitations = useCallback(async () => {
    if (!accessToken) {
      return;
    }

    setLoading(true);
    try {
      const nextInvitations = await fetchMyInvitations(accessToken);
      setInvitations(nextInvitations);
      setError(null);
    } catch (requestError) {
      if (requestError instanceof Error) {
        setError(requestError.message);
      }
    } finally {
      setLoading(false);
    }
  }, [accessToken]);

  useEffect(() => {
    void loadInvitations();
  }, [loadInvitations]);

  async function handleAccept(invitationId: string) {
    if (!accessToken) {
      return;
    }

    setSubmitting(true);
    try {
      await acceptInvitation(accessToken, invitationId);
      await refreshProfile();
      toast.success("Invitation accepted");
      await loadInvitations();
    } catch (requestError) {
      toast.error(requestError instanceof Error ? requestError.message : "Invitation acceptance failed");
    } finally {
      setSubmitting(false);
    }
  }

  if (loading) {
    return <LoadingState label="Buscando convites..." />;
  }

  return (
    <motion.section
      initial={{ opacity: 0, y: 18 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35 }}
      className="space-y-6"
    >
      <PageIntro
        eyebrow="Invitations"
        title="Doctor invitation acceptance"
        description="Página dedicada a `GET /my_invitations/` e `POST /doctor-invitations/:id/accept/`."
      />

      {error ? (
        <Panel className="border-rose-400/20 bg-rose-500/10 text-sm text-rose-100">
          {error}
        </Panel>
      ) : null}

      {invitations.length ? (
        <div className="grid gap-4">
          {invitations.map((invitation) => (
            <Panel key={invitation.id} className="space-y-4">
              <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
                <div className="space-y-2">
                  <div className="flex flex-wrap items-center gap-3">
                    <StatusPill status={invitation.status} />
                    <p className="text-lg font-semibold text-white">
                      {invitation.clinic_name}
                    </p>
                  </div>
                  <p className="text-sm text-slate-300">
                    Sent by {invitation.invited_by_email}
                  </p>
                </div>
                <button
                  type="button"
                  disabled={submitting}
                  onClick={() => void handleAccept(invitation.id)}
                  className="rounded-full bg-sky-500 px-5 py-3 text-sm font-semibold text-white transition hover:bg-sky-400 disabled:cursor-not-allowed disabled:opacity-60"
                >
                  Accept invitation
                </button>
              </div>
              <p className="text-xs uppercase tracking-[0.18em] text-slate-500">
                Expires {formatDateTime(invitation.expires_at)}
              </p>
            </Panel>
          ))}
        </div>
      ) : (
        <EmptyState
          title="No pending invitations"
          description="O endpoint `/my_invitations/` não retornou convites pendentes para o email autenticado."
        />
      )}
    </motion.section>
  );
}

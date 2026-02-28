import { FormEvent, useCallback, useEffect, useState } from "react";
import { motion } from "framer-motion";
import { toast } from "sonner";
import {
  createClinic,
  fetchClinicDoctors,
  fetchClinicInvitations,
  fetchClinics,
  fetchMyInvitations,
  getPageResults,
  inviteDoctor,
  removeDoctor,
} from "@/api/services";
import { useAuth } from "@/auth/AuthContext";
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

const createClinicDefaults = {
  name: "",
  cnpj: "",
  seatLimit: 5,
  subscriptionPlan: "starter",
};

export default function ClinicPage() {
  const { accessToken, refreshProfile, user } = useAuth();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [clinic, setClinic] = useState<Clinic | null>(null);
  const [doctors, setDoctors] = useState<UserSummary[]>([]);
  const [clinicInvitations, setClinicInvitations] = useState<DoctorInvitation[]>([]);
  const [myInvitations, setMyInvitations] = useState<DoctorInvitation[]>([]);
  const [createForm, setCreateForm] = useState(createClinicDefaults);
  const [inviteEmail, setInviteEmail] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const isClinicAdmin = user?.role === "CLINIC_ADMIN";

  const loadClinicData = useCallback(async () => {
    if (!accessToken) {
      return;
    }

    setLoading(true);
    try {
      const clinicsResponse = await fetchClinics(accessToken);
      const nextClinic = getPageResults(clinicsResponse)[0] ?? null;
      setClinic(nextClinic);

      const myInvitesPromise = fetchMyInvitations(accessToken);
      const doctorsPromise =
        nextClinic && isClinicAdmin
          ? fetchClinicDoctors(accessToken)
          : Promise.resolve([]);
      const clinicInvitationsPromise =
        nextClinic && isClinicAdmin
          ? fetchClinicInvitations(accessToken).then((payload) => getPageResults(payload))
          : Promise.resolve([]);

      const [nextMyInvitations, nextDoctors, nextClinicInvitations] =
        await Promise.all([
          myInvitesPromise,
          doctorsPromise,
          clinicInvitationsPromise,
        ]);

      setMyInvitations(nextMyInvitations);
      setDoctors(nextDoctors);
      setClinicInvitations(nextClinicInvitations);
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

  async function handleCreateClinic(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!accessToken) {
      return;
    }

    setSubmitting(true);
    try {
      await createClinic(accessToken, {
        name: createForm.name.trim(),
        cnpj: createForm.cnpj.trim(),
        seat_limit: createForm.seatLimit,
        subscription_plan: createForm.subscriptionPlan,
      });
      await refreshProfile();
      setCreateForm(createClinicDefaults);
      toast.success("Clinic created");
      await loadClinicData();
    } catch (requestError) {
      toast.error(requestError instanceof Error ? requestError.message : "Clinic creation failed");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleInviteDoctor(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!accessToken || !inviteEmail.trim()) {
      return;
    }

    setSubmitting(true);
    try {
      await inviteDoctor(accessToken, inviteEmail.trim().toLowerCase());
      setInviteEmail("");
      toast.success("Invitation sent");
      await loadClinicData();
    } catch (requestError) {
      toast.error(requestError instanceof Error ? requestError.message : "Invitation failed");
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
      toast.success("Doctor removed");
      await loadClinicData();
    } catch (requestError) {
      toast.error(requestError instanceof Error ? requestError.message : "Doctor removal failed");
    } finally {
      setSubmitting(false);
    }
  }

  if (loading) {
    return <LoadingState label="Carregando dados de tenancy..." />;
  }

  return (
    <motion.section
      initial={{ opacity: 0, y: 18 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35 }}
      className="space-y-6"
    >
      <PageIntro
        eyebrow="Clinic"
        title="Tenant and doctor workflow"
        description="Criação de clínica, convites, listagem de médicos e estado das invitations em linha com os endpoints `/api/clinics/*`."
      />

      {error ? <InlineNotice title="Clinic workflow error">{error}</InlineNotice> : null}

      {clinic ? (
        <div className="grid gap-6 xl:grid-cols-[0.85fr_1.15fr]">
          <Panel className="space-y-5">
            <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-400">
              Clinic profile
            </p>
            <h2 className="text-3xl font-semibold text-white">{clinic.name}</h2>
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
                <p className="text-xs uppercase tracking-[0.18em] text-slate-400">Plan</p>
                <p className="mt-2 text-lg font-semibold text-white">
                  {clinic.subscription_plan}
                </p>
              </div>
              <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
                <p className="text-xs uppercase tracking-[0.18em] text-slate-400">Seats</p>
                <p className="mt-2 text-lg font-semibold text-white">
                  {clinic.active_doctors_count} / {clinic.seat_limit}
                </p>
              </div>
            </div>
            <p className="text-sm leading-7 text-slate-300">
              Owner: {clinic.owner.email} · Created {formatDateTime(clinic.created_at)}
            </p>
            {!isClinicAdmin ? (
              <InlineNotice title="Read-only clinic membership">
                Seu usuário está vinculado a esta clínica, mas apenas `CLINIC_ADMIN`
                pode enviar convites ou remover médicos.
              </InlineNotice>
            ) : null}
          </Panel>

          <div className="space-y-6">
            {isClinicAdmin ? (
              <Panel className="space-y-5">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-400">
                    Invite doctor
                  </p>
                  <h2 className="mt-2 text-2xl font-semibold text-white">
                    Add a doctor to the clinic
                  </h2>
                </div>
                <form className="grid gap-4 md:grid-cols-[minmax(0,1fr)_auto]" onSubmit={handleInviteDoctor}>
                  <input
                    value={inviteEmail}
                    onChange={(event) => setInviteEmail(event.target.value)}
                    type="email"
                    placeholder="doctor@clinic.com"
                    className="rounded-2xl border border-white/10 bg-white/6 px-4 py-3 text-sm text-white outline-none placeholder:text-slate-500 focus:border-sky-300/50"
                  />
                  <button
                    type="submit"
                    disabled={submitting}
                    className="rounded-2xl bg-sky-500 px-5 py-3 text-sm font-semibold text-white transition hover:bg-sky-400 disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    Send invitation
                  </button>
                </form>
              </Panel>
            ) : null}

            <Panel className="space-y-4">
              <div className="flex items-center justify-between gap-4">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-400">
                    Active doctors
                  </p>
                  <h2 className="mt-2 text-2xl font-semibold text-white">
                    Team linked to the clinic
                  </h2>
                </div>
              </div>
              <div className="space-y-3">
                {doctors.length ? (
                  doctors.map((doctor) => (
                    <div
                      key={doctor.id}
                      className="flex flex-col gap-3 rounded-3xl border border-white/10 bg-white/5 px-4 py-4 md:flex-row md:items-center md:justify-between"
                    >
                      <div>
                        <p className="text-sm font-semibold text-white">{doctor.email}</p>
                        <p className="text-sm text-slate-300">{doctor.role}</p>
                      </div>
                      {isClinicAdmin ? (
                        <button
                          type="button"
                          onClick={() => void handleRemoveDoctor(doctor.id)}
                          disabled={submitting}
                          className="rounded-full border border-rose-300/25 bg-rose-500/10 px-4 py-2 text-sm font-semibold text-rose-100 transition hover:bg-rose-500/20 disabled:cursor-not-allowed disabled:opacity-60"
                        >
                          Remove doctor
                        </button>
                      ) : null}
                    </div>
                  ))
                ) : (
                  <p className="text-sm leading-7 text-slate-300">
                    Nenhum médico listado por este endpoint no momento.
                  </p>
                )}
              </div>
            </Panel>

            {isClinicAdmin ? (
              <Panel className="space-y-4">
                <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-400">
                  Invitations log
                </p>
                <div className="space-y-3">
                  {clinicInvitations.length ? (
                    clinicInvitations.map((invitation) => (
                      <div
                        key={invitation.id}
                        className="rounded-3xl border border-white/10 bg-white/5 px-4 py-4"
                      >
                        <div className="flex flex-wrap items-center gap-3">
                          <StatusPill status={invitation.status} />
                          <p className="text-sm font-semibold text-white">{invitation.email}</p>
                        </div>
                        <p className="mt-3 text-sm text-slate-300">
                          Invited by {invitation.invited_by_email}
                        </p>
                        <p className="mt-1 text-xs uppercase tracking-[0.18em] text-slate-500">
                          Expires {formatDateTime(invitation.expires_at)}
                        </p>
                      </div>
                    ))
                  ) : (
                    <p className="text-sm leading-7 text-slate-300">
                      Nenhum convite encontrado para esta clínica.
                    </p>
                  )}
                </div>
              </Panel>
            ) : null}
          </div>
        </div>
      ) : (
        <div className="grid gap-6 xl:grid-cols-[0.9fr_1.1fr]">
          <form onSubmit={handleCreateClinic}>
            <Panel className="space-y-5">
              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-400">
                  Create clinic
                </p>
                <h2 className="mt-2 text-2xl font-semibold text-white">
                  Onboard a new tenant
                </h2>
              </div>
              <div className="grid gap-4">
                <input
                  value={createForm.name}
                  onChange={(event) =>
                    setCreateForm((current) => ({ ...current, name: event.target.value }))
                  }
                  placeholder="Clinic name"
                  className="rounded-2xl border border-white/10 bg-white/6 px-4 py-3 text-sm text-white outline-none placeholder:text-slate-500 focus:border-sky-300/50"
                />
                <input
                  value={createForm.cnpj}
                  onChange={(event) =>
                    setCreateForm((current) => ({ ...current, cnpj: event.target.value }))
                  }
                  placeholder="CNPJ"
                  className="rounded-2xl border border-white/10 bg-white/6 px-4 py-3 text-sm text-white outline-none placeholder:text-slate-500 focus:border-sky-300/50"
                />
                <div className="grid gap-4 sm:grid-cols-2">
                  <input
                    value={createForm.seatLimit}
                    onChange={(event) =>
                      setCreateForm((current) => ({
                        ...current,
                        seatLimit: Number(event.target.value || 0),
                      }))
                    }
                    type="number"
                    min={1}
                    className="rounded-2xl border border-white/10 bg-white/6 px-4 py-3 text-sm text-white outline-none focus:border-sky-300/50"
                  />
                  <select
                    value={createForm.subscriptionPlan}
                    onChange={(event) =>
                      setCreateForm((current) => ({
                        ...current,
                        subscriptionPlan: event.target.value,
                      }))
                    }
                    className="rounded-2xl border border-white/10 bg-white/6 px-4 py-3 text-sm text-white outline-none focus:border-sky-300/50"
                  >
                    {["free", "starter", "professional", "enterprise"].map((value) => (
                      <option key={value} value={value} className="bg-slate-900">
                        {value}
                      </option>
                    ))}
                  </select>
                </div>
              </div>
              <button
                type="submit"
                disabled={submitting}
                className="rounded-2xl bg-sky-500 px-5 py-3 text-sm font-semibold text-white transition hover:bg-sky-400 disabled:cursor-not-allowed disabled:opacity-60"
              >
                Create clinic
              </button>
            </Panel>
          </form>

          {myInvitations.length ? (
            <Panel className="space-y-4">
              <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-400">
                Pending invitations
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
                    Sent by {invitation.invited_by_email}. Accept it from the Invitations page.
                  </p>
                </div>
              ))}
            </Panel>
          ) : (
            <EmptyState
              title="No clinic linked yet"
              description="Crie uma clínica nova ou aguarde um convite em `Invitations`. O backend também pode auto-aceitar quando existir exatamente um convite válido para o seu email."
            />
          )}
        </div>
      )}
    </motion.section>
  );
}

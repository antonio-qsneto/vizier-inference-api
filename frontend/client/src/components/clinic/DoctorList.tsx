import type { UserSummary } from "@/types/api";

interface DoctorListProps {
  doctors: UserSummary[];
  isAdmin: boolean;
  disablingActions?: boolean;
  onRemoveDoctor?: (doctorId: number) => Promise<void>;
}

export default function DoctorList({
  doctors,
  isAdmin,
  disablingActions = false,
  onRemoveDoctor,
}: DoctorListProps) {
  if (!doctors.length) {
    return (
      <p className="text-sm leading-7 text-slate-300">
        Nenhum médico ativo vinculado à clínica.
      </p>
    );
  }

  return (
    <div className="space-y-3">
      {doctors.map((doctor) => (
        <div
          key={doctor.id}
          className="flex flex-col gap-3 rounded-3xl border border-white/10 bg-white/5 px-4 py-4 md:flex-row md:items-center md:justify-between"
        >
          <div>
            <p className="text-sm font-semibold text-white">
              {doctor.full_name || doctor.email}
            </p>
            <p className="text-sm text-slate-300">{doctor.email}</p>
          </div>

          {isAdmin && onRemoveDoctor ? (
            <button
              type="button"
              onClick={() => void onRemoveDoctor(doctor.id)}
              disabled={disablingActions}
              className="rounded-full border border-rose-300/25 bg-rose-500/10 px-4 py-2 text-sm font-semibold text-rose-100 transition hover:bg-rose-500/20 disabled:cursor-not-allowed disabled:opacity-60"
            >
              Remove doctor
            </button>
          ) : null}
        </div>
      ))}
    </div>
  );
}

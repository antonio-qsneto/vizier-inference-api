import type { ReactNode } from "react";
import type { LucideIcon } from "lucide-react";
import { AlertTriangle, LoaderCircle } from "lucide-react";
import { cn } from "@/lib/utils";

export function Panel({
  className,
  children,
}: {
  className?: string;
  children: ReactNode;
}) {
  return (
    <div
      className={cn(
        "rounded-[16px] border border-white/8 bg-[linear-gradient(180deg,#313239,#2a2b31)] p-6 shadow-[0_24px_60px_rgba(0,0,0,0.24)]",
        className,
      )}
    >
      {children}
    </div>
  );
}

export function PageIntro({
  eyebrow,
  title,
  description,
  actions,
}: {
  eyebrow: string;
  title: string;
  description: string;
  actions?: ReactNode;
}) {
  return (
    <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
      <div className="max-w-3xl space-y-3">
        <p className="text-xs font-semibold uppercase tracking-[0.24em] text-sky-400">
          {eyebrow}
        </p>
        <h1 className="text-3xl font-semibold tracking-tight text-white sm:text-4xl">
          {title}
        </h1>
        <p className="max-w-2xl text-sm leading-7 text-slate-400 sm:text-base">
          {description}
        </p>
      </div>
      {actions ? <div className="flex flex-wrap gap-3">{actions}</div> : null}
    </div>
  );
}

const toneClasses: Record<string, string> = {
  COMPLETED: "border-emerald-400/20 bg-emerald-500/14 text-emerald-200",
  PROCESSING: "border-amber-400/20 bg-amber-500/14 text-amber-100",
  SUBMITTED: "border-sky-400/20 bg-sky-500/14 text-sky-100",
  QUEUED: "border-slate-400/20 bg-slate-500/14 text-slate-200",
  FAILED: "border-rose-400/20 bg-rose-500/14 text-rose-200",
  HEALTHY: "border-emerald-400/20 bg-emerald-500/14 text-emerald-200",
  OK: "border-emerald-400/20 bg-emerald-500/14 text-emerald-200",
};

export function StatusPill({ status }: { status: string | null | undefined }) {
  const label = status || "UNKNOWN";
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full border px-3 py-1 text-xs font-semibold uppercase tracking-[0.14em]",
        toneClasses[label] || "border-white/8 bg-white/6 text-slate-200",
      )}
    >
      {label}
    </span>
  );
}

export function MetricCard({
  label,
  value,
  detail,
  icon: Icon,
  tone = "blue",
}: {
  label: string;
  value: string;
  detail: string;
  icon?: LucideIcon;
  tone?: "blue" | "amber" | "emerald" | "rose";
}) {
  const toneStyles = {
    blue: "border-sky-400/20 bg-sky-500/12 text-sky-200",
    amber: "border-amber-400/20 bg-amber-500/12 text-amber-200",
    emerald: "border-emerald-400/20 bg-emerald-500/12 text-emerald-200",
    rose: "border-rose-400/20 bg-rose-500/12 text-rose-200",
  };

  return (
    <Panel className="space-y-4 p-5">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">
            {label}
          </p>
          <p className="mt-3 text-3xl font-semibold text-white">{value}</p>
        </div>
        {Icon ? (
          <div
            className={cn(
              "inline-flex h-12 w-12 items-center justify-center rounded-[14px] border",
              toneStyles[tone],
            )}
          >
            <Icon className="h-5 w-5" />
          </div>
        ) : null}
      </div>
      <p className="text-sm leading-6 text-slate-400">{detail}</p>
    </Panel>
  );
}

export function InlineNotice({
  title,
  children,
  tone = "info",
}: {
  title: string;
  children: ReactNode;
  tone?: "info" | "warning" | "danger";
}) {
  const tones = {
    info: "border-sky-400/20 bg-sky-500/10 text-sky-100",
    warning: "border-amber-400/20 bg-amber-500/10 text-amber-100",
    danger: "border-rose-400/20 bg-rose-500/10 text-rose-100",
  };

  return (
    <div className={cn("rounded-[14px] border p-4", tones[tone])}>
      <div className="flex items-start gap-3">
        <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
        <div className="space-y-1">
          <p className="text-sm font-semibold">{title}</p>
          <div className="text-sm leading-6 text-current/90">{children}</div>
        </div>
      </div>
    </div>
  );
}

export function EmptyState({
  title,
  description,
  action,
}: {
  title: string;
  description: string;
  action?: ReactNode;
}) {
  return (
    <Panel className="space-y-4 border-dashed border-white/12 bg-[#2c2d34] text-center">
      <p className="text-lg font-semibold text-white">{title}</p>
      <p className="mx-auto max-w-xl text-sm leading-7 text-slate-400">
        {description}
      </p>
      {action ? <div className="flex justify-center">{action}</div> : null}
    </Panel>
  );
}

export function LoadingState({
  label = "Carregando dados clínicos...",
}: {
  label?: string;
}) {
  return (
    <div className="flex min-h-[240px] items-center justify-center">
      <div className="flex items-center gap-3 rounded-[12px] border border-white/8 bg-[#2c2d34] px-5 py-3 text-sm text-slate-200">
        <LoaderCircle className="h-4 w-4 animate-spin text-sky-400" />
        <span>{label}</span>
      </div>
    </div>
  );
}

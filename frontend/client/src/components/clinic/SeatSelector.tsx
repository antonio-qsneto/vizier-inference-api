import { Minus, Plus } from "lucide-react";

interface SeatSelectorProps {
  value: number;
  onChange: (nextValue: number) => void;
  min?: number;
  max?: number;
  disabled?: boolean;
  label?: string;
  description?: string;
}

export default function SeatSelector({
  value,
  onChange,
  min = 1,
  max,
  disabled = false,
  label = "Assentos de médicos",
  description,
}: SeatSelectorProps) {
  const normalizedValue = Number.isFinite(value) ? Math.max(min, Math.floor(value)) : min;

  function clamp(nextValue: number) {
    let clamped = Math.max(min, Math.floor(nextValue));
    if (typeof max === "number") {
      clamped = Math.min(max, clamped);
    }
    return clamped;
  }

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between gap-3">
        <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">
          {label}
        </p>
        {description ? <p className="text-xs text-slate-400">{description}</p> : null}
      </div>

      <div className="flex items-center gap-2">
        <button
          type="button"
          disabled={disabled || normalizedValue <= min}
          onClick={() => onChange(clamp(normalizedValue - 1))}
          className="inline-flex h-10 w-10 items-center justify-center rounded-xl border border-white/12 bg-white/6 text-slate-100 transition hover:bg-white/10 disabled:cursor-not-allowed disabled:opacity-40"
        >
          <Minus className="h-4 w-4" />
        </button>

        <input
          type="number"
          min={min}
          max={max}
          value={normalizedValue}
          disabled={disabled}
          onChange={(event) => onChange(clamp(Number(event.target.value || min)))}
          className="h-10 w-full rounded-xl border border-white/12 bg-white/6 px-3 text-sm font-semibold text-white outline-none transition focus:border-sky-300/50 disabled:cursor-not-allowed disabled:opacity-60"
        />

        <button
          type="button"
          disabled={disabled || (typeof max === "number" && normalizedValue >= max)}
          onClick={() => onChange(clamp(normalizedValue + 1))}
          className="inline-flex h-10 w-10 items-center justify-center rounded-xl border border-white/12 bg-white/6 text-slate-100 transition hover:bg-white/10 disabled:cursor-not-allowed disabled:opacity-40"
        >
          <Plus className="h-4 w-4" />
        </button>
      </div>
    </div>
  );
}

import { Activity } from "lucide-react";
import type { RiskEstimate } from "../types";

const LEVEL_STYLES = {
  LOW: { bar: "bg-emerald-500", badge: "bg-emerald-100 text-emerald-800" },
  MEDIUM: { bar: "bg-amber-500", badge: "bg-amber-100 text-amber-800" },
  HIGH: { bar: "bg-red-500", badge: "bg-red-100 text-red-800" },
} as const;

export default function RiskCard({ risk, history }: { risk: RiskEstimate | null; history: number[] }) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <h2 className="mb-3 flex items-center gap-2 font-semibold">
        <Activity className="h-4 w-4 text-slate-500" /> Intervention risk
      </h2>

      {!risk || !risk.available || risk.probability == null || !risk.level ? (
        <p className="text-sm text-slate-500">{risk?.reason ?? "Appears after the first completed step."}</p>
      ) : (
        <>
          <div className="flex items-end justify-between">
            <p className="text-3xl font-bold">{Math.round(risk.probability * 100)}%</p>
            <span className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ${LEVEL_STYLES[risk.level].badge}`}>
              {risk.level}
            </span>
          </div>
          <div className="mt-2 h-2 overflow-hidden rounded-full bg-slate-100"
            role="progressbar" aria-valuenow={Math.round(risk.probability * 100)} aria-valuemin={0} aria-valuemax={100}>
            <div className={`h-full rounded-full transition-all ${LEVEL_STYLES[risk.level].bar}`}
              style={{ width: `${risk.probability * 100}%` }} />
          </div>
          <p className="mt-2 text-xs text-slate-500">
            Estimated chance that a human will need to step in after step {risk.step_index}.
          </p>

          {history.length > 1 && (
            <div className="mt-3 flex h-10 items-end gap-1" aria-label="Risk after each step">
              {history.map((p, i) => (
                <div key={i} title={`${Math.round(p * 100)}%`} className="w-full rounded-sm bg-slate-300"
                  style={{ height: `${Math.max(6, p * 100)}%` }} />
              ))}
            </div>
          )}

          {risk.factors.length > 0 && (
            <ul className="mt-3 space-y-1 text-xs text-slate-600">
              {risk.factors.map((f) => (
                <li key={f.feature} className="flex justify-between gap-2">
                  <span>{f.label}</span>
                  <span className={f.effect > 0 ? "font-semibold text-red-700" : "font-semibold text-emerald-700"}>
                    {f.effect > 0 ? "+" : ""}{Math.round(f.effect * 100)} pts
                  </span>
                </li>
              ))}
            </ul>
          )}

          <p className="mt-3 text-[11px] text-slate-400">Model: {risk.model?.replace(/_/g, " ")}</p>
          {risk.warning && (
            <p className="mt-2 rounded-lg bg-amber-50 px-2 py-1.5 text-[11px] text-amber-800">
              {risk.data_source === "synthetic" ? "Trained on SYNTHETIC data: " : ""}
              this is an illustration of the method, not a proven prediction.
            </p>
          )}
        </>
      )}
    </div>
  );
}
import type { Intervention } from "../types";
import { INTERVENTION_LABELS } from "../utils/labels";

export default function InterventionsPanel({ items }: { items: Intervention[] }) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <h2 className="mb-3 font-semibold">Human interventions</h2>
      {items.length === 0 ? (
        <p className="text-sm text-slate-500">None yet.</p>
      ) : (
        <ul className="max-h-72 space-y-2 overflow-y-auto pr-1">
          {items.map((i) => (
            <li key={i.id} className="rounded-lg bg-slate-50 px-3 py-2 text-sm">
              <p className="font-medium">
                @{i.username ?? "unknown"} · {INTERVENTION_LABELS[i.type]}
              </p>
              {(i.content || i.target) && (
                <p className="mt-0.5 break-words text-slate-600">
                  {i.type === "CHANGE_SOURCE" ? `${i.target} → ${i.content}` : i.content ?? i.target}
                </p>
              )}
              {i.result && <p className="mt-0.5 text-xs text-slate-400">{i.result}</p>}
              <time className="text-xs text-slate-400">{new Date(i.created_at).toLocaleTimeString()}</time>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
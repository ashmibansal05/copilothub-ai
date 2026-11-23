import { Scale } from "lucide-react";
import type { Conflict, ConflictSide } from "../types";
import { PRIORITY_STYLES } from "../utils/labels";

function Side({ label, side }: { label: string; side: ConflictSide }) {
  return (
    <div className="rounded-lg bg-white p-3 text-sm shadow-sm">
      <p className="text-xs font-semibold uppercase text-slate-500">{label}</p>
      <p className="mt-1 break-words font-medium text-slate-900">{side.description}</p>
      <p className="mt-1 flex flex-wrap items-center gap-2 text-xs text-slate-500">
        <span className={`rounded-full px-1.5 py-0.5 font-semibold ${PRIORITY_STYLES[side.priority]}`}>
          {side.priority}
        </span>
        <span>
          @{side.created_by_username ?? "unknown"}
          {side.created_by_role && ` (${side.created_by_role.toLowerCase()})`}
        </span>
      </p>
    </div>
  );
}

interface Props {
  conflicts: Conflict[];
  isOwner: boolean;
  busy: boolean;
  onResolve: (conflictId: string, winnerConstraintId: string | null) => void;
}

export default function ConflictCard({ conflicts, isOwner, busy, onResolve }: Props) {
  if (conflicts.length === 0) return null;
  return (
    <div className="space-y-3">
      {conflicts.map((c) => (
        <div
          key={c.id}
          role="alert"
          className={`rounded-2xl border-2 p-5 shadow-sm ${c.requires_resolution ? "border-red-300 bg-red-50" : "border-amber-300 bg-amber-50"}`}
        >
          <h2 className="flex items-center gap-2 font-semibold text-slate-900">
            <Scale className="h-5 w-5" /> Conflicting instructions
            {c.requires_resolution && (
              <span className="rounded-full bg-red-600 px-2 py-0.5 text-xs font-semibold text-white">
                agent is waiting for the owner
              </span>
            )}
          </h2>
          <div className="mt-3 grid gap-3 sm:grid-cols-2">
            <Side label="Instruction A (older)" side={c.constraint_a} />
            <Side label="Instruction B (newer)" side={c.constraint_b} />
          </div>
          <p className="mt-3 text-sm text-slate-700">
            <span className="font-medium">Rule applied:</span> {c.rule_applied}
          </p>
          {c.provisional && <p className="mt-1 text-sm text-slate-700">{c.provisional}</p>}

          {isOwner ? (
            <div className="mt-4 flex flex-wrap gap-2">
              <button className="btn-primary" disabled={busy} onClick={() => onResolve(c.id, c.constraint_a.constraint_id)}>
                Keep A
              </button>
              <button className="btn-primary" disabled={busy} onClick={() => onResolve(c.id, c.constraint_b.constraint_id)}>
                Keep B
              </button>
              <button className="btn-secondary" disabled={busy} onClick={() => onResolve(c.id, null)}>
                Remove both
              </button>
            </div>
          ) : (
            <p className="mt-3 text-sm text-slate-600">Only the session owner can resolve this conflict.</p>
          )}
        </div>
      ))}
    </div>
  );
}
import { Ban, CheckCircle2, FileText, Star, X } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import type { Constraint, ConstraintAction } from "../types";
import { ACTION_LABELS, PRIORITY_STYLES } from "../utils/labels";

const ICONS: Record<ConstraintAction, { icon: LucideIcon; color: string }> = {
  EXCLUDE_SOURCE: { icon: Ban, color: "text-red-600" },
  INCLUDE_SOURCE: { icon: CheckCircle2, color: "text-emerald-600" },
  PREFER_SOURCE: { icon: Star, color: "text-amber-500" },
  INSTRUCTION: { icon: FileText, color: "text-slate-500" },
};

interface Props {
  constraints: Constraint[];
  canEdit: boolean;
  onRemove: (id: string) => void;
}

export default function ConstraintsPanel({ constraints, canEdit, onRemove }: Props) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <h2 className="mb-3 font-semibold">Active constraints ({constraints.length})</h2>
      {constraints.length === 0 ? (
        <p className="text-sm text-slate-500">No constraints. Add one to steer the agent, e.g. “don't use Wikipedia”.</p>
      ) : (
        <ul className="space-y-2">
          {constraints.map((c) => {
            const { icon: Icon, color } = ICONS[c.action];
            return (
              <li key={c.id} className="flex items-start gap-2 rounded-lg bg-slate-50 px-3 py-2">
                <Icon className={`mt-0.5 h-4 w-4 shrink-0 ${color}`} aria-hidden />
                <div className="min-w-0 flex-1">
                  <p className="break-words text-sm text-slate-800">{c.description}</p>
                  <p className="mt-1 flex flex-wrap items-center gap-2 text-xs text-slate-500">
                    <span>{ACTION_LABELS[c.action]}</span>
                    <span className={`rounded-full px-1.5 py-0.5 font-semibold ${PRIORITY_STYLES[c.priority]}`}>
                      {c.priority}
                    </span>
                    {c.created_by_username && <span>by @{c.created_by_username}</span>}
                  </p>
                </div>
                {canEdit && (
                  <button onClick={() => onRemove(c.id)} className="text-slate-400 hover:text-red-600"
                    aria-label={`Remove constraint: ${c.description}`}>
                    <X className="h-4 w-4" />
                  </button>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
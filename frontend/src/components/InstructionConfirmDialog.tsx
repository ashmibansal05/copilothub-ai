import { Loader2, X } from "lucide-react";
import { useState } from "react";
import type { FormEvent } from "react";
import { getErrorMessage } from "../services/api";
import type {
  Constraint, ConstraintAction, InstructionResult, InterventionPayload, InterventionType, Priority, UserRole,
} from "../types";
import { INTERVENTION_LABELS } from "../utils/labels";

const TYPES: InterventionType[] = [
  "REJECT_SOURCE", "CHANGE_SOURCE", "ADD_CONSTRAINT", "REMOVE_CONSTRAINT", "CORRECT", "ADD_INFORMATION",
  "COMMENT", "APPROVE", "REJECT", "PAUSE", "RESUME", "MODIFY_TASK",
];
const ACTIONS: { value: ConstraintAction; label: string }[] = [
  { value: "EXCLUDE_SOURCE", label: "Don't use a source" },
  { value: "PREFER_SOURCE", label: "Prefer a source or type" },
  { value: "INCLUDE_SOURCE", label: "Explicitly allow a source" },
  { value: "INSTRUCTION", label: "General instruction (advisory)" },
];

interface Props {
  result: InstructionResult;
  constraints: Constraint[];
  role: UserRole;
  onClose: () => void;
  onConfirm: (payload: InterventionPayload) => Promise<void>;
}

export default function InstructionConfirmDialog({ result, constraints, role, onClose, onConfirm }: Props) {
  const p = result.proposal;
  const [type, setType] = useState<InterventionType>(p.type);
  const [content, setContent] = useState(p.content ?? "");
  const [target, setTarget] = useState(p.target ?? "");
  const [action, setAction] = useState<ConstraintAction>(p.action ?? "INSTRUCTION");
  const [priority, setPriority] = useState<Priority>(p.priority ?? "MEDIUM");
  const [constraintId, setConstraintId] = useState(p.constraint_id ?? "");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const allowedTypes = TYPES.filter((t) => role === "OWNER" || t !== "MODIFY_TASK");
  const needsContent = ["CORRECT", "ADD_INFORMATION", "COMMENT", "MODIFY_TASK", "CHANGE_SOURCE"].includes(type);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const payload: InterventionPayload = { type, origin_text: result.text };
      if (["CORRECT", "ADD_INFORMATION", "COMMENT", "MODIFY_TASK", "REJECT"].includes(type)) payload.content = content || undefined;
      if (type === "REJECT_SOURCE") payload.target = target;
      if (type === "CHANGE_SOURCE") { payload.target = target; payload.content = content; }
      if (type === "ADD_CONSTRAINT") { payload.action = action; payload.target = target; payload.priority = priority; }
      if (type === "REMOVE_CONSTRAINT") payload.constraint_id = constraintId;
      await onConfirm(payload);
      onClose();
    } catch (err) {
      setError(getErrorMessage(err));
      setBusy(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4"
      onMouseDown={(e) => e.target === e.currentTarget && onClose()}
      onKeyDown={(e) => e.key === "Escape" && onClose()}>
      <form onSubmit={submit} role="dialog" aria-modal="true" aria-labelledby="confirm-title"
        className="w-full max-w-lg space-y-4 rounded-2xl bg-white p-6 shadow-xl">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h2 id="confirm-title" className="text-lg font-bold">Is this what you meant?</h2>
            <p className="mt-1 break-words text-sm text-slate-600">“{result.text}”</p>
          </div>
          <button type="button" onClick={onClose} className="text-slate-400 hover:text-slate-600" aria-label="Close">
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-900">
          <p>
            I understood this as <strong>{result.intent.replace(/_/g, " ").toLowerCase()}</strong>
            {" "}({Math.round(result.confidence * 100)}% sure{result.method === "rule" ? ", by a fixed rule" : ""}).
          </p>
          {result.reason && <p className="mt-1">{result.reason}</p>}
          {result.alternatives.length > 1 && (
            <p className="mt-1 text-xs">
              Other possibilities: {result.alternatives.slice(1).map((a) => `${a.intent.toLowerCase().replace(/_/g, " ")} (${Math.round(a.confidence * 100)}%)`).join(", ")}
            </p>
          )}
        </div>

        {error && <div role="alert" className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div>}

        <div>
          <label htmlFor="ic-type" className="mb-1 block text-sm font-medium">Action</label>
          <select id="ic-type" className="input" value={type} onChange={(e) => setType(e.target.value as InterventionType)}>
            {allowedTypes.map((t) => <option key={t} value={t}>{INTERVENTION_LABELS[t]}</option>)}
          </select>
        </div>

        {type === "ADD_CONSTRAINT" && (
          <>
            <select className="input" value={action} onChange={(e) => setAction(e.target.value as ConstraintAction)} aria-label="Rule">
              {ACTIONS.map((a) => <option key={a.value} value={a.value}>{a.label}</option>)}
            </select>
            <select className="input" value={priority} onChange={(e) => setPriority(e.target.value as Priority)} aria-label="Priority">
              <option value="HIGH">High priority</option><option value="MEDIUM">Medium priority</option><option value="LOW">Low priority</option>
            </select>
          </>
        )}
        {["REJECT_SOURCE", "CHANGE_SOURCE", "ADD_CONSTRAINT"].includes(type) && (
          <div>
            <label htmlFor="ic-target" className="mb-1 block text-sm font-medium">
              {type === "CHANGE_SOURCE" ? "Source to stop using" : type === "ADD_CONSTRAINT" && action === "INSTRUCTION" ? "Instruction" : "Source name, website or type"}
            </label>
            <input id="ic-target" className="input" required minLength={2} maxLength={300} value={target} onChange={(e) => setTarget(e.target.value)} />
          </div>
        )}
        {type === "REMOVE_CONSTRAINT" && (
          <div>
            <label htmlFor="ic-constraint" className="mb-1 block text-sm font-medium">Which constraint?</label>
            <select id="ic-constraint" className="input" required value={constraintId} onChange={(e) => setConstraintId(e.target.value)}>
              <option value="">Choose…</option>
              {constraints.map((c) => <option key={c.id} value={c.id}>{c.description}</option>)}
            </select>
          </div>
        )}
        {(needsContent || type === "REJECT") && (
          <div>
            <label htmlFor="ic-content" className="mb-1 block text-sm font-medium">
              {type === "CHANGE_SOURCE" ? "Source to use instead" : type === "MODIFY_TASK" ? "New task" : type === "REJECT" ? "What should change? (optional)" : "Text"}
            </label>
            {type === "CHANGE_SOURCE"
              ? <input id="ic-content" className="input" required maxLength={300} value={content} onChange={(e) => setContent(e.target.value)} />
              : <textarea id="ic-content" className="input min-h-[90px]" required={type !== "REJECT"} maxLength={2000} value={content} onChange={(e) => setContent(e.target.value)} />}
          </div>
        )}

        <div className="flex justify-end gap-2">
          <button type="button" onClick={onClose} className="btn-secondary">Cancel</button>
          <button type="submit" disabled={busy} className="btn-primary">
            {busy && <Loader2 className="h-4 w-4 animate-spin" />} Confirm
          </button>
        </div>
      </form>
    </div>
  );
}
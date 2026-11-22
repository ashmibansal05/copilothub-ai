import { Loader2, X } from "lucide-react";
import { useState } from "react";
import type { FormEvent } from "react";
import { getErrorMessage } from "../services/api";
import type { ConstraintAction, InterventionPayload, Priority } from "../types";

export type DialogKind =
  | "COMMENT" | "CORRECT" | "ADD_INFORMATION" | "MODIFY_TASK"
  | "CONSTRAINT" | "REJECT" | "REQUEST_REVIEW";

const TEXT_CONFIG: Record<
  Exclude<DialogKind, "CONSTRAINT">,
  { title: string; hint: string; label: string; placeholder: string; required: boolean; submit: string }
> = {
  COMMENT: {
    title: "Add a comment", hint: "Visible to everyone in the session. It does not change the agent's behaviour.",
    label: "Comment", placeholder: "Looks good so far", required: true, submit: "Post comment",
  },
  CORRECT: {
    title: "Correct the agent", hint: "Saved to the session memory. The agent takes relevant corrections into account in later steps and drafts.",
    label: "Correction", placeholder: "Use euros, not dollars, for all prices", required: true, submit: "Send correction",
  },
  ADD_INFORMATION: {
    title: "Add information", hint: "A fact the agent should know. Saved to the session memory.",
    label: "Information", placeholder: "The team has two developers and no ops engineer", required: true, submit: "Add information",
  },
  MODIFY_TASK: {
    title: "Modify the task", hint: "The agent will re-plan at its next checkpoint using the new task.",
    label: "New task", placeholder: "", required: true, submit: "Update task",
  },
  REJECT: {
    title: "Reject", hint: "Tell the agent what to change. The feedback is used to revise the draft.",
    label: "What should change? (optional)", placeholder: "Add a cost comparison table", required: false, submit: "Reject",
  },
  REQUEST_REVIEW: {
    title: "Request a review", hint: "The agent will stop at its next checkpoint and wait for someone to approve or reject.",
    label: "Note (optional)", placeholder: "Please check the sources before it continues", required: false, submit: "Request review",
  },
};

const ACTIONS: { value: ConstraintAction; label: string; placeholder: string }[] = [
  { value: "EXCLUDE_SOURCE", label: "Don't use a source", placeholder: "Wikipedia" },
  { value: "PREFER_SOURCE", label: "Prefer a source or type", placeholder: "official documentation" },
  { value: "INCLUDE_SOURCE", label: "Explicitly allow a source", placeholder: "Wikipedia" },
  { value: "INSTRUCTION", label: "General instruction (advisory)", placeholder: "Keep the report under 500 words" },
];

interface Props {
  kind: DialogKind;
  initialText?: string;
  onClose: () => void;
  onSubmit: (payload: InterventionPayload) => Promise<void>;
}

export default function InterventionDialog({ kind, initialText = "", onClose, onSubmit }: Props) {
  const [content, setContent] = useState(initialText);
  const [target, setTarget] = useState("");
  const [action, setAction] = useState<ConstraintAction>("EXCLUDE_SOURCE");
  const [priority, setPriority] = useState<Priority>("MEDIUM");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const isConstraint = kind === "CONSTRAINT";
  const text = isConstraint ? null : TEXT_CONFIG[kind];
  const actionCfg = ACTIONS.find((a) => a.value === action)!;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      if (isConstraint) {
        await onSubmit({ type: "ADD_CONSTRAINT", action, target, priority });
      } else {
        await onSubmit({ type: kind, content: content || undefined });
      }
      onClose();
    } catch (err) {
      setError(getErrorMessage(err));
      setSubmitting(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4"
      onMouseDown={(e) => e.target === e.currentTarget && onClose()}
      onKeyDown={(e) => e.key === "Escape" && onClose()}
    >
      <form
        onSubmit={submit}
        role="dialog"
        aria-modal="true"
        aria-labelledby="dialog-title"
        className="w-full max-w-lg space-y-4 rounded-2xl bg-white p-6 shadow-xl"
      >
        <div className="flex items-start justify-between gap-4">
          <div>
            <h2 id="dialog-title" className="text-lg font-bold">
              {isConstraint ? "Add a constraint" : text!.title}
            </h2>
            <p className="mt-1 text-sm text-slate-500">
              {isConstraint
                ? "Becomes a structured rule the agent must follow in all future steps."
                : text!.hint}
            </p>
          </div>
          <button type="button" onClick={onClose} className="text-slate-400 hover:text-slate-600" aria-label="Close">
            <X className="h-5 w-5" />
          </button>
        </div>

        {error && (
          <div role="alert" className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div>
        )}

        {isConstraint ? (
          <>
            <div>
              <label htmlFor="c-action" className="mb-1 block text-sm font-medium">Rule</label>
              <select id="c-action" className="input" value={action}
                onChange={(e) => setAction(e.target.value as ConstraintAction)}>
                {ACTIONS.map((a) => <option key={a.value} value={a.value}>{a.label}</option>)}
              </select>
            </div>
            <div>
              <label htmlFor="c-target" className="mb-1 block text-sm font-medium">
                {action === "INSTRUCTION" ? "Instruction" : "Source name, website or type"}
              </label>
              <input id="c-target" className="input" autoFocus required minLength={2} maxLength={300}
                placeholder={actionCfg.placeholder} value={target} onChange={(e) => setTarget(e.target.value)} />
            </div>
            <div>
              <label htmlFor="c-priority" className="mb-1 block text-sm font-medium">Priority</label>
              <select id="c-priority" className="input" value={priority}
                onChange={(e) => setPriority(e.target.value as Priority)}>
                <option value="HIGH">High</option>
                <option value="MEDIUM">Medium</option>
                <option value="LOW">Low</option>
              </select>
            </div>
          </>
        ) : (
          <div>
            <label htmlFor="i-content" className="mb-1 block text-sm font-medium">{text!.label}</label>
            <textarea id="i-content" className="input min-h-[110px]" autoFocus
              required={text!.required} maxLength={2000} placeholder={text!.placeholder}
              value={content} onChange={(e) => setContent(e.target.value)} />
          </div>
        )}

        <div className="flex justify-end gap-2">
          <button type="button" onClick={onClose} className="btn-secondary">Cancel</button>
          <button type="submit" disabled={submitting} className="btn-primary">
            {submitting && <Loader2 className="h-4 w-4 animate-spin" />}
            {isConstraint ? "Add constraint" : text!.submit}
          </button>
        </div>
      </form>
    </div>
  );
}
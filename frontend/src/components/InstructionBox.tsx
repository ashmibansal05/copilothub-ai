import { Loader2, Send } from "lucide-react";
import { useState } from "react";
import type { FormEvent } from "react";
import { getErrorMessage } from "../services/api";
import type { InstructionResult } from "../types";
import { INTERVENTION_LABELS } from "../utils/labels";

interface Props {
  onSubmit: (text: string) => Promise<InstructionResult>;
  onNeedsConfirmation: (result: InstructionResult) => void;
}

export default function InstructionBox({ onSubmit, onNeedsConfirmation }: Props) {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [feedback, setFeedback] = useState<{ tone: "ok" | "info" | "error"; message: string } | null>(null);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (text.trim().length < 2) return;
    setBusy(true);
    setFeedback(null);
    try {
      const result = await onSubmit(text.trim());
      if (result.applied) {
        const what = result.intervention?.result ?? INTERVENTION_LABELS[result.proposal.type];
        setFeedback({ tone: "ok", message: `Applied (${Math.round(result.confidence * 100)}% sure: ${result.intent.replace(/_/g, " ").toLowerCase()}). ${what}` });
        setText("");
      } else if (!result.allowed) {
        setFeedback({ tone: "info", message: result.reason ?? "You cannot do that." });
      } else {
        onNeedsConfirmation(result);
      }
    } catch (err) {
      setFeedback({ tone: "error", message: getErrorMessage(err) });
    } finally {
      setBusy(false);
    }
  };

  const tones = { ok: "text-emerald-700", info: "text-slate-600", error: "text-red-700" };
  return (
    <div>
      <form onSubmit={submit} className="flex gap-2">
        <input
          className="input" value={text} maxLength={1000} onChange={(e) => setText(e.target.value)}
          placeholder="Tell the agent what to do, e.g. “Don't use Wikipedia” or “Prefer official documentation”"
          aria-label="Instruction for the agent"
        />
        <button type="submit" className="btn-primary" disabled={busy || text.trim().length < 2}>
          {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
          <span className="hidden sm:inline">Send</span>
        </button>
      </form>
      {feedback && (
        <p role="status" className={`mt-1 text-sm ${tones[feedback.tone]}`}>{feedback.message}</p>
      )}
    </div>
  );
}
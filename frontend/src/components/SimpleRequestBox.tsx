import { Send, Loader2 } from "lucide-react";
import { useState } from "react";
import type { FormEvent } from "react";
import { getErrorMessage } from "../services/api";
import { sessionService } from "../services/sessionService";

/** Plain-language work requests do not require the optional NLP classifier. */
export default function SimpleRequestBox({ sessionId }: { sessionId: string }) {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState(false);

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (text.trim().length < 3 || busy) return;
    setBusy(true);
    setMessage("");
    setError(false);
    try {
      const result = await sessionService.requestWork(sessionId, text.trim());
      setMessage(result.message);
      setText("");
    } catch (err) {
      setError(true);
      setMessage(getErrorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  return <div className="space-y-2">
    <label htmlFor="shared-ai-request" className="text-sm font-semibold">Ask your AI teammate</label>
    <form onSubmit={submit} className="flex gap-2">
      <input id="shared-ai-request" className="input" value={text} maxLength={2000}
        onChange={e => setText(e.target.value)}
        placeholder="Describe a change, new requirement, or something to investigate..." />
      <button type="submit" className="btn-primary" disabled={busy || text.trim().length < 3}>
        {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
        <span className="hidden sm:inline">Send</span>
      </button>
    </form>
    {message && <p role="status" className={`text-xs ${error ? "text-red-700" : "text-emerald-700"}`}>{message}</p>}
    <p className="text-xs text-slate-500">Your team's requests are saved. Code changes are queued while the AI is busy. Research notes become part of the shared project context.</p>
  </div>;
}

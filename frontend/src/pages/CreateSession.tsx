import { Loader2 } from "lucide-react";
import { useState } from "react";
import type { FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { getErrorMessage } from "../services/api";
import { sessionService } from "../services/sessionService";

export default function CreateSession() {
  const navigate = useNavigate();
  const [name, setName] = useState("");
  const [task, setTask] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const session = await sessionService.create(name, task);
      navigate(`/sessions/${session.id}`);
    } catch (err) {
      setError(getErrorMessage(err));
      setSubmitting(false);
    }
  };

  return (
    <div className="mx-auto max-w-2xl">
      <h1 className="text-2xl font-bold">Create a session</h1>
      <p className="mt-1 text-slate-600">
        You become the owner. You'll get an editor invite link and a viewer invite link to share.
      </p>

      <form onSubmit={onSubmit} className="mt-6 space-y-4 rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
        {error && (
          <div role="alert" className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">
            {error}
          </div>
        )}
        <div>
          <label htmlFor="name" className="mb-1 block text-sm font-medium">Session name</label>
          <input id="name" className="input" required minLength={3} maxLength={120}
            placeholder="Cloud platform research" value={name} onChange={(e) => setName(e.target.value)} />
        </div>
        <div>
          <label htmlFor="task" className="mb-1 block text-sm font-medium">Task for the agent</label>
          <textarea id="task" className="input min-h-[120px]" required minLength={10} maxLength={2000}
            placeholder="Prepare a report comparing AWS, Microsoft Azure and Google Cloud for a small startup."
            value={task} onChange={(e) => setTask(e.target.value)} />
        </div>
        <button type="submit" disabled={submitting} className="btn-primary">
          {submitting && <Loader2 className="h-4 w-4 animate-spin" />}
          Create session
        </button>
      </form>
    </div>
  );
}
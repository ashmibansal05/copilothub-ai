import { FileText } from "lucide-react";
import { useState } from "react";
import { getErrorMessage } from "../services/api";
import type { ReportDetail, ReportSummary } from "../types";

export default function ReportsPanel({
  reports,
  onOpen,
}: {
  reports: ReportSummary[];
  onOpen: (id: string) => Promise<ReportDetail>;
}) {
  const [open, setOpen] = useState<ReportDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  const toggle = async (id: string) => {
    if (open?.id === id) return setOpen(null);
    try {
      setError(null);
      setOpen(await onOpen(id));
    } catch (err) {
      setError(getErrorMessage(err));
    }
  };

  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <h2 className="mb-3 flex items-center gap-2 font-semibold">
        <FileText className="h-4 w-4 text-slate-500" /> Saved reports ({reports.length})
      </h2>
      {error && <div role="alert" className="mb-2 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div>}
      {reports.length === 0 ? (
        <p className="text-sm text-slate-500">No drafts yet. The agent can save drafts with its save_report tool.</p>
      ) : (
        <ul className="space-y-2">
          {reports.map((r) => (
            <li key={r.id} className="rounded-lg bg-slate-50 px-3 py-2 text-sm">
              <button className="w-full text-left" onClick={() => toggle(r.id)}>
                <p className="font-medium">{r.title}</p>
                <p className="text-xs text-slate-500">
                  {r.status} · by {r.origin.toLowerCase()} · {r.chars} characters · {new Date(r.created_at).toLocaleTimeString()}
                </p>
              </button>
              {open?.id === r.id && (
                // Rendered as plain text on purpose: report content is never interpreted as HTML.
                <pre className="mt-2 max-h-64 overflow-y-auto whitespace-pre-wrap break-words rounded bg-white p-2 text-xs text-slate-700">
                  {open.content}
                </pre>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
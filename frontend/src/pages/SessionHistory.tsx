import { Loader2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { RoleBadge, StatusBadge } from "../components/StatusBadge";
import { getErrorMessage } from "../services/api";
import { sessionService } from "../services/sessionService";
import type { SessionSummary } from "../types";

const STATUSES = ["ALL", "CREATED", "RUNNING", "PAUSED", "WAITING_FOR_APPROVAL", "COMPLETED", "FAILED", "CANCELLED"];

export default function SessionHistory() {
  const [sessions, setSessions] = useState<SessionSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("ALL");

  useEffect(() => {
    sessionService.list().then(setSessions).catch((e) => setError(getErrorMessage(e)));
  }, []);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return (sessions ?? []).filter(
      (s) => (status === "ALL" || s.status === status) && (!q || `${s.name} ${s.task}`.toLowerCase().includes(q))
    );
  }, [sessions, query, status]);

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-bold">Session history</h1>
        <p className="text-slate-600">Every session you belong to, with shortcuts to its report, analytics and records.</p>
      </div>

      <div className="flex flex-wrap gap-3">
        <input className="input max-w-sm" placeholder="Search by name or task…" value={query}
          onChange={(e) => setQuery(e.target.value)} aria-label="Search sessions" />
        <select className="input max-w-xs" value={status} onChange={(e) => setStatus(e.target.value)} aria-label="Filter by status">
          {STATUSES.map((s) => <option key={s} value={s}>{s === "ALL" ? "All statuses" : s.replace(/_/g, " ").toLowerCase()}</option>)}
        </select>
      </div>

      {error && <div role="alert" className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div>}
      {sessions === null && !error && (
        <div className="flex justify-center py-10"><Loader2 className="h-6 w-6 animate-spin text-brand-600" aria-label="Loading" /></div>
      )}
      {sessions && filtered.length === 0 && (
        <div className="rounded-2xl border border-dashed border-slate-300 bg-white p-10 text-center text-sm text-slate-500">
          {sessions.length === 0 ? "You have no sessions yet." : "No session matches your filters."}
        </div>
      )}

      {filtered.length > 0 && (
        <div className="overflow-x-auto rounded-2xl border border-slate-200 bg-white shadow-sm">
          <table className="w-full text-left text-sm">
            <thead className="bg-slate-50 text-xs text-slate-500">
              <tr><th className="px-4 py-2">Session</th><th>Status</th><th>My role</th><th>Members</th><th>Created</th><th className="pr-4">Open</th></tr>
            </thead>
            <tbody>
              {filtered.map((s) => (
                <tr key={s.id} className="border-t border-slate-100">
                  <td className="max-w-xs px-4 py-2">
                    <Link to={`/sessions/${s.id}`} className="font-medium text-brand-700 hover:underline">{s.name}</Link>
                    <p className="truncate text-xs text-slate-500">{s.task}</p>
                  </td>
                  <td><StatusBadge status={s.status} /></td>
                  <td><RoleBadge role={s.my_role} /></td>
                  <td>{s.member_count}</td>
                  <td className="whitespace-nowrap">{new Date(s.created_at).toLocaleDateString()}</td>
                  <td className="space-x-3 whitespace-nowrap pr-4">
                    <Link className="text-brand-600 hover:underline" to={`/sessions/${s.id}/report`}>Report</Link>
                    <Link className="text-brand-600 hover:underline" to={`/sessions/${s.id}/analytics`}>Analytics</Link>
                    <Link className="text-brand-600 hover:underline" to={`/sessions/${s.id}/records`}>Records</Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
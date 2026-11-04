import { Loader2, Plus, Users } from "lucide-react";
import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { RoleBadge, StatusBadge } from "../components/StatusBadge";
import { useAuth } from "../contexts/AuthContext";
import { getErrorMessage } from "../services/api";
import { sessionService } from "../services/sessionService";
import type { SessionSummary } from "../types";

export default function Dashboard() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [sessions, setSessions] = useState<SessionSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [code, setCode] = useState("");

  useEffect(() => {
    sessionService
      .list()
      .then(setSessions)
      .catch((err) => setError(getErrorMessage(err)));
  }, []);

  if (!user) return null;

  const onJoin = (e: FormEvent) => {
    e.preventDefault();
    const trimmed = code.trim().toUpperCase();
    if (trimmed) navigate(`/join/${trimmed}`);
  };

  return (
    <div className="space-y-8">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold">Hello, {user.full_name.split(" ")[0]} 👋</h1>
          <p className="text-slate-600">Your collaborative agent sessions.</p>
        </div>
        <Link to="/sessions/new" className="btn-primary">
          <Plus className="h-4 w-4" /> New session
        </Link>
      </div>

      <form onSubmit={onJoin} className="flex max-w-md gap-2">
        <input
          className="input uppercase"
          placeholder="Have an invite code? e.g. ABC12345"
          value={code}
          maxLength={12}
          onChange={(e) => setCode(e.target.value)}
          aria-label="Invite code"
        />
        <button type="submit" className="btn-secondary" disabled={!code.trim()}>
          Join
        </button>
      </form>

      {error && (
        <div role="alert" className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">
          {error}
        </div>
      )}

      {sessions === null && !error && (
        <div className="flex justify-center py-10">
          <Loader2 className="h-6 w-6 animate-spin text-brand-600" aria-label="Loading sessions" />
        </div>
      )}

      {sessions && sessions.length === 0 && (
        <div className="rounded-2xl border border-dashed border-slate-300 bg-white p-10 text-center">
          <h2 className="font-semibold">No sessions yet</h2>
          <p className="mt-1 text-sm text-slate-500">
            Create a session, or join one with an invite code or link.
          </p>
        </div>
      )}

      {sessions && sessions.length > 0 && (
        <ul className="grid gap-4 md:grid-cols-2">
          {sessions.map((s) => (
            <li key={s.id}>
              <Link
                to={`/sessions/${s.id}`}
                className="block h-full rounded-2xl border border-slate-200 bg-white p-5 shadow-sm transition hover:border-brand-500 hover:shadow"
              >
                <div className="flex items-start justify-between gap-2">
                  <h3 className="font-semibold">{s.name}</h3>
                  <StatusBadge status={s.status} />
                </div>
                <p className="mt-1 line-clamp-2 text-sm text-slate-600">{s.task}</p>
                <div className="mt-4 flex items-center gap-3 text-xs text-slate-500">
                  <RoleBadge role={s.my_role} />
                  <span className="inline-flex items-center gap-1">
                    <Users className="h-3.5 w-3.5" /> {s.member_count}
                  </span>
                  <span>by @{s.owner_username}</span>
                </div>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
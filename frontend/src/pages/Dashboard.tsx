import { CalendarClock, Mail, ShieldCheck, UserCircle } from "lucide-react";
import { useAuth } from "../contexts/AuthContext";

export default function Dashboard() {
  const { user } = useAuth();
  if (!user) return null;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Hello, {user.full_name.split(" ")[0]} 👋</h1>
        <p className="text-slate-600">You are logged in. Session management arrives in Phase 3.</p>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <h2 className="mb-4 font-semibold">Your account</h2>
          <dl className="space-y-3 text-sm">
            <div className="flex items-center gap-3"><UserCircle className="h-4 w-4 text-slate-400" />
              <dt className="sr-only">Username</dt><dd>@{user.username}</dd></div>
            <div className="flex items-center gap-3"><Mail className="h-4 w-4 text-slate-400" />
              <dt className="sr-only">Email</dt><dd>{user.email}</dd></div>
            <div className="flex items-center gap-3"><ShieldCheck className="h-4 w-4 text-slate-400" />
              <dt className="sr-only">Role</dt>
              <dd><span className="rounded-full bg-brand-50 px-2 py-0.5 text-xs font-semibold text-brand-700">{user.role}</span></dd></div>
            <div className="flex items-center gap-3"><CalendarClock className="h-4 w-4 text-slate-400" />
              <dt className="sr-only">Joined</dt><dd>Joined {new Date(user.created_at).toLocaleDateString()}</dd></div>
          </dl>
        </div>

        <div className="rounded-2xl border border-dashed border-slate-300 bg-white p-6 text-center">
          <h2 className="font-semibold">No sessions yet</h2>
          <p className="mt-1 text-sm text-slate-500">
            Create or join a collaborative agent session — coming in Phase 3.
          </p>
        </div>
      </div>
    </div>
  );
}
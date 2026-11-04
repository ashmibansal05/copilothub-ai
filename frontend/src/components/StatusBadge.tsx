import type { AgentStatus, UserRole } from "../types";

const STATUS_STYLES: Record<AgentStatus, string> = {
  CREATED: "bg-slate-100 text-slate-700",
  PLANNING: "bg-sky-100 text-sky-700",
  RUNNING: "bg-emerald-100 text-emerald-700",
  WAITING_FOR_APPROVAL: "bg-amber-100 text-amber-800",
  PAUSED: "bg-amber-100 text-amber-800",
  COMPLETED: "bg-brand-100 text-brand-700",
  FAILED: "bg-red-100 text-red-700",
  CANCELLED: "bg-slate-200 text-slate-600",
};

export function StatusBadge({ status }: { status: AgentStatus }) {
  return (
    <span className={`inline-flex rounded-full px-2.5 py-0.5 text-xs font-semibold ${STATUS_STYLES[status]}`}>
      {status.replace(/_/g, " ")}
    </span>
  );
}

const ROLE_STYLES: Record<UserRole, string> = {
  OWNER: "bg-brand-100 text-brand-700",
  EDITOR: "bg-sky-100 text-sky-700",
  VIEWER: "bg-slate-100 text-slate-600",
};

export function RoleBadge({ role }: { role: UserRole }) {
  return (
    <span className={`inline-flex rounded-full px-2 py-0.5 text-xs font-semibold ${ROLE_STYLES[role]}`}>
      {role}
    </span>
  );
}
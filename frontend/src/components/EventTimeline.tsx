import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  ListChecks,
  MessageSquare,
  Pause,
  Play,
  RefreshCw,
  UserMinus,
  UserPlus,
  Users,
  Wrench,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import type { SessionEvent } from "../types";

interface Described {
  icon: LucideIcon;
  text: string;
  color: string;
}

function describe(e: SessionEvent): Described {
  const who: string = e.payload?.actor?.username ?? e.payload?.user?.username ?? "Someone";
  switch (e.type) {
    case "AGENT_STARTED":
      return { icon: Play, text: `${who} started the session`, color: "text-emerald-600" };
    case "STATUS_CHANGED":
      return {
        icon: RefreshCw,
        text: `Status: ${e.payload.previous_status} → ${e.payload.status}`,
        color: "text-sky-600",
      };
    case "STEP_STARTED":
      return {
        icon: ListChecks,
        text:
          e.payload.phase === "PLAN"
            ? "Planning the research"
            : `Step ${e.payload.step_index}/${e.payload.total_steps}: ${e.payload.step}`,
        color: "text-brand-600",
      };
    case "STEP_COMPLETED":
      return { icon: CheckCircle2, text: String(e.payload.summary ?? "Step completed"), color: "text-emerald-600" };
    case "TOOL_STARTED":
      return { icon: Wrench, text: `Calling ${e.payload.tool}`, color: "text-slate-500" };
    case "TOOL_COMPLETED":
      return e.payload.success
        ? { icon: Wrench, text: `${e.payload.tool} finished (${e.payload.duration_ms} ms)`, color: "text-slate-600" }
        : { icon: AlertTriangle, text: `${e.payload.tool} failed: ${e.payload.error ?? "error"}`, color: "text-red-600" };
    case "AGENT_MESSAGE":
      return { icon: MessageSquare, text: String(e.payload.text ?? ""), color: "text-slate-600" };
    case "COMPLETED":
      return { icon: CheckCircle2, text: "Agent completed the task", color: "text-emerald-600" };
    case "FAILED":
      return { icon: AlertTriangle, text: `Agent failed: ${e.payload.error ?? "unknown error"}`, color: "text-red-600" };
    case "PAUSED":
      return { icon: Pause, text: `${who} paused the session`, color: "text-amber-600" };
    case "RESUMED":
      return { icon: Play, text: `${who} resumed the session`, color: "text-emerald-600" };
    case "USER_JOINED":
      return { icon: UserPlus, text: `${who} is online`, color: "text-slate-500" };
    case "USER_LEFT":
      return { icon: UserMinus, text: `${who} went offline`, color: "text-slate-400" };
    case "MEMBER_JOINED":
      return {
        icon: Users,
        text: `${who} joined as ${String(e.payload.role).toLowerCase()}`,
        color: "text-brand-600",
      };
    default:
      return { icon: Activity, text: e.type, color: "text-slate-500" };
  }
}

export default function EventTimeline({ events }: { events: SessionEvent[] }) {
  if (events.length === 0) {
    return <p className="text-sm text-slate-500">No activity yet.</p>;
  }
  return (
    <ol className="space-y-3">
      {[...events].reverse().map((e) => {
        const { icon: Icon, text, color } = describe(e);
        return (
          <li key={e.id} className="flex gap-3">
            <Icon className={`mt-0.5 h-4 w-4 shrink-0 ${color}`} aria-hidden />
            <div className="min-w-0">
              <p className="break-words text-sm text-slate-800">{text}</p>
              <time className="text-xs text-slate-400">
                {new Date(e.created_at).toLocaleTimeString()}
              </time>
            </div>
          </li>
        );
      })}
    </ol>
  );
}
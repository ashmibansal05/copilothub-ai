import { Check, Copy, Eye, Loader2, Pause, Play, Square, Wifi, WifiOff } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import AgentPanel from "../components/AgentPanel";
import EventTimeline from "../components/EventTimeline";
import { RoleBadge, StatusBadge } from "../components/StatusBadge";
import ToolActivity from "../components/ToolActivity";
import { useSessionSocket } from "../hooks/useSessionSocket";
import type { ConnectionStatus } from "../hooks/useSessionSocket";
import { getErrorMessage } from "../services/api";
import { sessionService } from "../services/sessionService";
import type { AgentState, ControlAction, SessionDetail, SessionEvent } from "../types";
import { applyAgentEvent, emptyAgentState } from "../utils/agentState";

// Events that have their own panels; keeping them out of the timeline avoids noise.
const HIDDEN_IN_TIMELINE = new Set(["TOOL_STARTED", "STEP_COMPLETED", "AGENT_MESSAGE"]);

const MESSAGE_STYLES: Record<string, string> = {
  agent: "bg-slate-50 text-slate-800",
  system: "bg-slate-50 text-slate-500",
  warning: "bg-amber-50 text-amber-800",
  escalation: "bg-red-50 text-red-800",
};

function ConnectionBadge({ status }: { status: ConnectionStatus }) {
  if (status === "connected")
    return (
      <span className="inline-flex items-center gap-1.5 rounded-full bg-emerald-50 px-2.5 py-1 text-xs font-medium text-emerald-700">
        <Wifi className="h-3.5 w-3.5" /> Live
      </span>
    );
  if (status === "connecting")
    return (
      <span className="inline-flex items-center gap-1.5 rounded-full bg-amber-50 px-2.5 py-1 text-xs font-medium text-amber-700">
        <Loader2 className="h-3.5 w-3.5 animate-spin" /> Connecting
      </span>
    );
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full bg-red-50 px-2.5 py-1 text-xs font-medium text-red-700">
      <WifiOff className="h-3.5 w-3.5" /> Disconnected
    </span>
  );
}

function CopyRow({ label, value }: { label: string; value: string }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    await navigator.clipboard.writeText(value);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };
  return (
    <div>
      <p className="mb-1 text-xs font-medium text-slate-500">{label}</p>
      <div className="flex gap-2">
        <input readOnly value={value} className="input !py-1.5 text-xs" onFocus={(e) => e.target.select()} />
        <button onClick={copy} className="btn-secondary !px-2.5" aria-label={`Copy ${label}`}>
          {copied ? <Check className="h-4 w-4 text-emerald-600" /> : <Copy className="h-4 w-4" />}
        </button>
      </div>
    </div>
  );
}

export default function SessionWorkspace() {
  const { id } = useParams<{ id: string }>();
  const [session, setSession] = useState<SessionDetail | null>(null);
  const [agent, setAgent] = useState<AgentState | null>(null);
  const [events, setEvents] = useState<SessionEvent[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [busy, setBusy] = useState<ControlAction | null>(null);

  const mergeEvents = useCallback((incoming: SessionEvent[]) => {
    setEvents((prev) => {
      const map = new Map(prev.map((e) => [e.id, e]));
      incoming.forEach((e) => map.set(e.id, e));
      return [...map.values()].sort(
        (a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime()
      );
    });
  }, []);

  const loadSession = useCallback(async () => {
    if (!id) return;
    try {
      setSession(await sessionService.get(id));
    } catch (err) {
      setLoadError(getErrorMessage(err));
    }
  }, [id]);

  useEffect(() => {
    if (!id) return;
    loadSession();
    sessionService.events(id).then(mergeEvents).catch(() => undefined);
    sessionService.state(id).then(setAgent).catch(() => undefined);
  }, [id, loadSession, mergeEvents]);

  const handleEvent = useCallback(
    (e: SessionEvent) => {
      if (e.type === "CONNECTED") {
        setSession((s) => (s ? { ...s, status: e.payload.status } : s));
        return;
      }
      if (e.type === "STATUS_CHANGED") {
        setSession((s) => (s ? { ...s, status: e.payload.status } : s));
      }
      if (e.type === "MEMBER_JOINED") loadSession();
      setAgent((prev) => (prev ? applyAgentEvent(prev, e) : prev));
      mergeEvents([e]);
    },
    [loadSession, mergeEvents]
  );

  const { status: connStatus, online } = useSessionSocket(id, handleEvent);

  const run = async (action: ControlAction) => {
    if (!id) return;
    setBusy(action);
    setActionError(null);
    try {
      await sessionService.control(id, action);
      loadSession(); // fallback in case the socket is down
    } catch (err) {
      setActionError(getErrorMessage(err));
    } finally {
      setBusy(null);
    }
  };

  if (loadError) {
    return (
      <div className="mx-auto max-w-md rounded-2xl border border-slate-200 bg-white p-8 text-center">
        <p className="text-red-700">{loadError}</p>
        <Link to="/dashboard" className="btn-secondary mt-4">Back to dashboard</Link>
      </div>
    );
  }
  if (!session) {
    return (
      <div className="flex justify-center py-20">
        <Loader2 className="h-8 w-8 animate-spin text-brand-600" aria-label="Loading session" />
      </div>
    );
  }

  const role = session.my_role;
  const status = session.status;
  const agentState = agent ?? emptyAgentState(session.id, session.task, status);
  const canStart = role === "OWNER" && status === "CREATED";
  const canPause = role !== "VIEWER" && (status === "RUNNING" || status === "PLANNING");
  const canResume = role !== "VIEWER" && status === "PAUSED";
  const canStop = role === "OWNER" && ["CREATED", "RUNNING", "PLANNING", "PAUSED"].includes(status);
  const onlineIds = new Set(online.map((u) => u.user_id));
  const agentMessages = events.filter((e) => e.type === "AGENT_MESSAGE");
  const timelineEvents = events.filter((e) => !HIDDEN_IN_TIMELINE.has(e.type));
  const origin = window.location.origin;

  return (
    <div className="space-y-4">
      {/* Session header */}
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-slate-200 bg-white px-5 py-3 shadow-sm">
        <div>
          <h1 className="text-lg font-bold leading-tight">{session.name}</h1>
          <p className="text-xs text-slate-500">Session ID: {session.id.slice(0, 8)}</p>
        </div>
        <div className="flex items-center gap-2">
          <StatusBadge status={status} />
          <RoleBadge role={role} />
          <ConnectionBadge status={connStatus} />
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-[280px_1fr_300px]">
        {/* Left: timeline */}
        <aside className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <h2 className="mb-3 font-semibold">Activity timeline</h2>
          <div className="max-h-[640px] overflow-y-auto pr-1">
            <EventTimeline events={timelineEvents} />
          </div>
        </aside>

        {/* Center: task, agent, tools, messages */}
        <section className="min-w-0 space-y-4">
          <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <h2 className="font-semibold">Current task</h2>
            <p className="mt-2 text-sm text-slate-700">{session.task}</p>
          </div>

          <AgentPanel agent={agentState} status={status} />
          <ToolActivity events={events} />

          <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <h2 className="mb-3 font-semibold">Agent messages</h2>
            {agentMessages.length === 0 ? (
              <p className="text-sm text-slate-500">Nothing yet. Messages appear here in real time.</p>
            ) : (
              <ul className="max-h-96 space-y-2 overflow-y-auto pr-1">
                {agentMessages.map((m) => (
                  <li
                    key={m.id}
                    className={`whitespace-pre-wrap break-words rounded-lg px-3 py-2 text-sm ${
                      MESSAGE_STYLES[String(m.payload.kind)] ?? MESSAGE_STYLES.system
                    }`}
                  >
                    {String(m.payload.text)}
                    {m.payload.simulated && (
                      <span className="ml-2 text-[10px] font-semibold uppercase text-amber-700">simulated</span>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </div>
        </section>

        {/* Right: collaborators + invites */}
        <aside className="space-y-4">
          <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <h2 className="mb-3 font-semibold">Collaborators ({session.members.length})</h2>
            <ul className="space-y-3">
              {session.members.map((m) => (
                <li key={m.user_id} className="flex items-center justify-between gap-2">
                  <div className="flex min-w-0 items-center gap-2">
                    <span
                      className={`h-2.5 w-2.5 shrink-0 rounded-full ${onlineIds.has(m.user_id) ? "bg-emerald-500" : "bg-slate-300"}`}
                      title={onlineIds.has(m.user_id) ? "Online" : "Offline"}
                    />
                    <span className="truncate text-sm">{m.full_name}</span>
                  </div>
                  <RoleBadge role={m.role} />
                </li>
              ))}
            </ul>
          </div>

          {role === "OWNER" && session.editor_code && session.viewer_code && (
            <div className="space-y-3 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
              <h2 className="font-semibold">Invite links</h2>
              <CopyRow label="Editor link" value={`${origin}/join/${session.editor_code}`} />
              <CopyRow label="Viewer link" value={`${origin}/join/${session.viewer_code}`} />
            </div>
          )}
        </aside>
      </div>

      {/* Bottom action bar */}
      <div className="sticky bottom-3 rounded-2xl border border-slate-200 bg-white/95 p-3 shadow-lg backdrop-blur">
        {actionError && (
          <div role="alert" className="mb-2 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">
            {actionError}
          </div>
        )}
        <div className="flex flex-wrap items-center gap-2">
          {role === "VIEWER" && (
            <span className="inline-flex items-center gap-2 text-sm text-slate-500">
              <Eye className="h-4 w-4" /> View-only: you can watch but not control the agent.
            </span>
          )}
          {canStart && (
            <button className="btn-primary" disabled={busy !== null} onClick={() => run("start")}>
              <Play className="h-4 w-4" /> Start agent
            </button>
          )}
          {canPause && (
            <button className="btn-secondary" disabled={busy !== null} onClick={() => run("pause")}>
              <Pause className="h-4 w-4" /> Pause
            </button>
          )}
          {canResume && (
            <button className="btn-primary" disabled={busy !== null} onClick={() => run("resume")}>
              <Play className="h-4 w-4" /> Resume
            </button>
          )}
          {canStop && (
            <button className="btn-secondary !text-red-700" disabled={busy !== null} onClick={() => run("stop")}>
              <Square className="h-4 w-4" /> Stop
            </button>
          )}
          {role !== "VIEWER" && !canStart && !canPause && !canResume && !canStop && (
            <span className="text-sm text-slate-500">No actions available while the session is {status.toLowerCase()}.</span>
          )}
        </div>
      </div>
    </div>
  );
}
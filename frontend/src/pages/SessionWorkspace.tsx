import {
  Check, Copy, Eye, Hand, Loader2, MessageSquare, Pause, Play, Plus, ShieldPlus, Square, Wifi, WifiOff,
} from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import AgentPanel from "../components/AgentPanel";
import ApprovalCard from "../components/ApprovalCard";
import ConflictCard from "../components/ConflictCard";
import ConstraintsPanel from "../components/ConstraintsPanel";
import DocumentsPanel from "../components/DocumentsPanel";
import InstructionBox from "../components/InstructionBox";
import InstructionConfirmDialog from "../components/InstructionConfirmDialog";
import ReportsPanel from "../components/ReportsPanel";
import EventTimeline from "../components/EventTimeline";
import InterventionDialog from "../components/InterventionDialog";
import type { DialogKind } from "../components/InterventionDialog";
import InterventionsPanel from "../components/InterventionsPanel";
import MemoryPanel from "../components/MemoryPanel";
import { RoleBadge, StatusBadge } from "../components/StatusBadge";
import ToolActivity from "../components/ToolActivity";
import { useSessionSocket } from "../hooks/useSessionSocket";
import type { ConnectionStatus } from "../hooks/useSessionSocket";
import { getErrorMessage } from "../services/api";
import { sessionService } from "../services/sessionService";
import type {
  AgentState, ControlAction, DocumentInfo, InstructionResult, InterventionPayload, MemoryItem,
  ReportSummary, SessionDetail, SessionEvent,
} from "../types";
import { applyAgentEvent, emptyAgentState } from "../utils/agentState";

const HIDDEN_IN_TIMELINE = new Set(["TOOL_STARTED", "STEP_COMPLETED", "AGENT_MESSAGE"]);
const TERMINAL = ["COMPLETED", "FAILED", "CANCELLED"];

const MESSAGE_STYLES: Record<string, string> = {
  agent: "bg-slate-50 text-slate-800",
  system: "bg-slate-50 text-slate-500",
  warning: "bg-amber-50 text-amber-800",
  escalation: "bg-red-50 text-red-800",
  constraint: "bg-brand-50 text-brand-700",
};

function isHidden(e: SessionEvent): boolean {
  if (HIDDEN_IN_TIMELINE.has(e.type)) return true;
  // pause/resume already have their own timeline entries
  return e.type === "HUMAN_INTERVENTION" && ["PAUSE", "RESUME"].includes(e.payload.intervention?.type);
}

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
  const [memory, setMemory] = useState<MemoryItem[]>([]);
  const [documents, setDocuments] = useState<DocumentInfo[]>([]);
  const [reports, setReports] = useState<ReportSummary[]>([]);
  const [pendingInstruction, setPendingInstruction] = useState<InstructionResult | null>(null);
  const [dialog, setDialog] = useState<DialogKind | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

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

  const loadMemory = useCallback(() => {
    if (!id) return;
    sessionService.memory(id).then((m) => setMemory(m.items)).catch(() => undefined);
  }, [id]);

  useEffect(() => {
    if (!id) return;
    loadSession();
    loadMemory();
    sessionService.events(id).then(mergeEvents).catch(() => undefined);
    sessionService.state(id).then(setAgent).catch(() => undefined);
    sessionService.documents(id).then(setDocuments).catch(() => undefined);
    sessionService.reports(id).then(setReports).catch(() => undefined);
  }, [id, loadSession, loadMemory, mergeEvents]);

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
      if (e.type === "HUMAN_INTERVENTION") {
        const iv = e.payload.intervention;
        if (iv?.type === "MODIFY_TASK" && iv.content) {
          setSession((s) => (s ? { ...s, task: iv.content } : s));
        }
        loadMemory();
      }
      if (e.type === "APPROVAL_COMPLETED" || e.type === "CONFLICT_RESOLVED") loadMemory();
      if (["DOCUMENT_ADDED", "DOCUMENT_READY", "DOCUMENT_FAILED"].includes(e.type) && e.payload.document) {
        const doc = e.payload.document as DocumentInfo;
        setDocuments((prev) =>
          prev.some((d) => d.id === doc.id) ? prev.map((d) => (d.id === doc.id ? doc : d)) : [...prev, doc]
        );
      }
      if (e.type === "DOCUMENT_REMOVED") {
        setDocuments((prev) => prev.filter((d) => d.id !== e.payload.document_id));
      }
      if (e.type === "REPORT_SAVED" && e.payload.report) {
        sessionService.reports(id!).then(setReports).catch(() => undefined);
      }
      setAgent((prev) => (prev ? applyAgentEvent(prev, e) : prev));
      mergeEvents([e]);
    },
    [id, loadSession, loadMemory, mergeEvents]
  );

  const { status: connStatus, online } = useSessionSocket(id, handleEvent);

  const attempt = async (key: string, fn: () => Promise<unknown>) => {
    setBusy(key);
    setActionError(null);
    try {
      await fn();
      loadSession(); // fallback in case the socket is down
    } catch (err) {
      setActionError(getErrorMessage(err));
    } finally {
      setBusy(null);
    }
  };

  const control = (action: ControlAction) => attempt(action, () => sessionService.control(id!, action));
  const quick = (payload: InterventionPayload) => attempt(payload.type, () => sessionService.intervene(id!, payload));
  const submitDialog = async (payload: InterventionPayload) => {
    await sessionService.intervene(id!, payload);
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
  const pending = agentState.pending_approval;
  const ended = TERMINAL.includes(status);
  const isOwner = role === "OWNER";
  const canGuide = role !== "VIEWER" && !ended;
  const canStart = isOwner && status === "CREATED";
  const canPause = role !== "VIEWER" && (status === "RUNNING" || status === "PLANNING");
  const canResume = role !== "VIEWER" && status === "PAUSED";
  const canStop = isOwner && !ended;
  const canReview = role !== "VIEWER" && ["RUNNING", "PLANNING", "PAUSED"].includes(status) && !pending;
  const onlineIds = new Set(online.map((u) => u.user_id));
  const agentMessages = events.filter((e) => e.type === "AGENT_MESSAGE");
  const timelineEvents = events.filter((e) => !isHidden(e));
  const origin = window.location.origin;

  return (
    <div className="space-y-4">
      {dialog && (
        <InterventionDialog
          kind={dialog}
          initialText={dialog === "MODIFY_TASK" ? session.task : ""}
          onClose={() => setDialog(null)}
          onSubmit={submitDialog}
        />
      )}

      {pendingInstruction && (
        <InstructionConfirmDialog
          result={pendingInstruction}
          constraints={agentState.active_constraints}
          role={role}
          onClose={() => setPendingInstruction(null)}
          onConfirm={async (payload) => {
            await sessionService.intervene(id!, payload);
          }}
        />
      )}

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
          <div className="max-h-[720px] overflow-y-auto pr-1">
            <EventTimeline events={timelineEvents} />
          </div>
        </aside>

        {/* Center */}
        <section className="min-w-0 space-y-4">
          <ConflictCard
            conflicts={agentState.open_conflicts}
            isOwner={isOwner}
            busy={busy !== null}
            onResolve={(conflictId, winner) =>
              attempt("resolve", () => sessionService.resolveConflict(id!, conflictId, winner))
            }
          />

          {pending && (
            <ApprovalCard
              approval={pending}
              canDecide={role !== "VIEWER"}
              canModify={isOwner}
              busy={busy !== null}
              onApprove={() => quick({ type: "APPROVE" })}
              onReject={() => setDialog("REJECT")}
              onModify={() => setDialog("MODIFY_TASK")}
            />
          )}

          <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <h2 className="font-semibold">Current task</h2>
            <p className="mt-2 text-sm text-slate-700">{session.task}</p>
          </div>

          <AgentPanel agent={agentState} status={status} />
          <ToolActivity
            events={events}
            onRejectSource={canGuide ? (publisher) => quick({ type: "REJECT_SOURCE", target: publisher }) : undefined}
          />

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

          <div className="grid gap-4 md:grid-cols-2">
            <InterventionsPanel items={agentState.human_interventions} />
            <MemoryPanel items={memory} />
          </div>
        </section>

        {/* Right */}
        <aside className="space-y-4">
          <ConstraintsPanel
            constraints={agentState.active_constraints}
            canEdit={canGuide}
            onRemove={(cid) => attempt("remove", () => sessionService.removeConstraint(id!, cid))}
          />

          <DocumentsPanel
            documents={documents}
            canManage={canGuide}
            onUpload={async (file, meta) => {
              await sessionService.uploadDocument(id!, file, meta);
            }}
            onDelete={(docId) => sessionService.deleteDocument(id!, docId)}
            onSearch={(q) => sessionService.searchDocuments(id!, q)}
            onPreview={(docId) => sessionService.documentChunks(id!, docId)}
          />

          <ReportsPanel reports={reports} onOpen={(rid) => sessionService.report(id!, rid)} />

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

          {isOwner && session.editor_code && session.viewer_code && (
            <div className="space-y-3 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
              <h2 className="font-semibold">Invite links</h2>
              <CopyRow label="Editor link" value={`${origin}/join/${session.editor_code}`} />
              <CopyRow label="Viewer link" value={`${origin}/join/${session.viewer_code}`} />
            </div>
          )}
        </aside>
      </div>

      {/* Bottom action bar */}
      <div className="sticky bottom-3 space-y-2 rounded-2xl border border-slate-200 bg-white/95 p-3 shadow-lg backdrop-blur">
        {actionError && (
          <div role="alert" className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{actionError}</div>
        )}
        {role === "VIEWER" && (
          <span className="inline-flex items-center gap-2 text-sm text-slate-500">
            <Eye className="h-4 w-4" /> View-only: you can watch but not control the agent.
          </span>
        )}
        {role !== "VIEWER" && (
          <>
            {canGuide && (
              <InstructionBox
                onSubmit={(text) => sessionService.instruct(id!, text)}
                onNeedsConfirmation={setPendingInstruction}
              />
            )}
            <div className="flex flex-wrap items-center gap-2">
              <button className="btn-secondary" onClick={() => setDialog("COMMENT")}>
                <MessageSquare className="h-4 w-4" /> Comment
              </button>
              <button className="btn-secondary" disabled={!canGuide} onClick={() => setDialog("CORRECT")}>
                <Hand className="h-4 w-4" /> Correct
              </button>
              <button className="btn-secondary" disabled={!canGuide} onClick={() => setDialog("ADD_INFORMATION")}>
                <Plus className="h-4 w-4" /> Add info
              </button>
              <button className="btn-secondary" disabled={!canGuide} onClick={() => setDialog("CONSTRAINT")}>
                <ShieldPlus className="h-4 w-4" /> Add constraint
              </button>
              {canReview && (
                <button className="btn-secondary" onClick={() => setDialog("REQUEST_REVIEW")}>Request review</button>
              )}
              {isOwner && !ended && (
                <button className="btn-secondary" onClick={() => setDialog("MODIFY_TASK")}>Modify task</button>
              )}
            </div>
            <div className="flex flex-wrap items-center gap-2">
              {pending && (
                <>
                  <button className="btn-primary" disabled={busy !== null} onClick={() => quick({ type: "APPROVE" })}>Approve</button>
                  <button className="btn-secondary" disabled={busy !== null} onClick={() => setDialog("REJECT")}>Reject</button>
                </>
              )}
              {canStart && (
                <button className="btn-primary" disabled={busy !== null} onClick={() => control("start")}>
                  <Play className="h-4 w-4" /> Start agent
                </button>
              )}
              {canPause && (
                <button className="btn-secondary" disabled={busy !== null} onClick={() => quick({ type: "PAUSE" })}>
                  <Pause className="h-4 w-4" /> Pause
                </button>
              )}
              {canResume && (
                <button className="btn-primary" disabled={busy !== null} onClick={() => quick({ type: "RESUME" })}>
                  <Play className="h-4 w-4" /> Resume
                </button>
              )}
              {canStop && (
                <button className="btn-secondary !text-red-700" disabled={busy !== null} onClick={() => control("stop")}>
                  <Square className="h-4 w-4" /> Stop
                </button>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
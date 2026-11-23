import { ArrowLeft, Loader2 } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useToast } from "../contexts/ToastContext";
import { getErrorMessage } from "../services/api";
import { sessionService } from "../services/sessionService";
import type { Conflict, DocumentInfo, Intervention, SessionDetail, SourceLog, ToolExecutionRow } from "../types";
import { INTERVENTION_LABELS } from "../utils/labels";

type Tab = "interventions" | "conflicts" | "documents" | "tools" | "danger";

const when = (iso: string) => new Date(iso).toLocaleString();
const Empty = ({ text }: { text: string }) => <p className="py-8 text-center text-sm text-slate-500">{text}</p>;

function Table({ head, children }: { head: string[]; children: React.ReactNode }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-sm">
        <thead className="text-xs text-slate-500"><tr>{head.map((h) => <th key={h} className="px-2 py-1.5">{h}</th>)}</tr></thead>
        <tbody>{children}</tbody>
      </table>
    </div>
  );
}

export default function SessionRecords() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const toast = useToast();
  const [tab, setTab] = useState<Tab>("interventions");
  const [session, setSession] = useState<SessionDetail | null>(null);
  const [interventions, setInterventions] = useState<Intervention[]>([]);
  const [conflicts, setConflicts] = useState<Conflict[]>([]);
  const [documents, setDocuments] = useState<DocumentInfo[]>([]);
  const [sources, setSources] = useState<SourceLog[]>([]);
  const [tools, setTools] = useState<ToolExecutionRow[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [armed, setArmed] = useState(false);
  const [deleting, setDeleting] = useState(false);

  useEffect(() => {
    if (!id) return;
    sessionService.get(id).then(setSession).catch((e) => setError(getErrorMessage(e)));
    sessionService.interventions(id).then(setInterventions).catch(() => undefined);
    sessionService.conflicts(id).then(setConflicts).catch(() => undefined);
    sessionService.documents(id).then(setDocuments).catch(() => undefined);
    sessionService.sources(id).then(setSources).catch(() => undefined);
    sessionService.toolExecutions(id).then(setTools).catch(() => undefined);
  }, [id]);

  const remove = async () => {
    if (!id) return;
    setDeleting(true);
    try {
      await sessionService.deleteSession(id);
      toast.success("The session and all of its data were deleted.");
      navigate("/dashboard", { replace: true });
    } catch (err) {
      toast.error(getErrorMessage(err));
      setDeleting(false);
    }
  };

  if (error) return <div role="alert" className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div>;
  if (!session) return <div className="flex justify-center py-20"><Loader2 className="h-8 w-8 animate-spin text-brand-600" aria-label="Loading" /></div>;

  const tabs: { key: Tab; label: string }[] = [
    { key: "interventions", label: `Interventions (${interventions.length})` },
    { key: "conflicts", label: `Conflicts (${conflicts.length})` },
    { key: "documents", label: `Documents & sources` },
    { key: "tools", label: `Tool log (${tools.length})` },
    ...(session.my_role === "OWNER" ? [{ key: "danger" as Tab, label: "Danger zone" }] : []),
  ];

  return (
    <div className="space-y-4">
      <Link to={`/sessions/${id}`} className="inline-flex items-center gap-1 text-sm text-slate-600 hover:text-slate-900">
        <ArrowLeft className="h-4 w-4" /> Back to the session
      </Link>
      <h1 className="text-2xl font-bold">{session.name}: records</h1>

      <div role="tablist" aria-label="Records" className="flex flex-wrap gap-2">
        {tabs.map((t) => (
          <button key={t.key} role="tab" aria-selected={tab === t.key} onClick={() => setTab(t.key)}
            className={tab === t.key ? "btn-primary" : "btn-secondary"}>{t.label}</button>
        ))}
      </div>

      <div role="tabpanel" className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        {tab === "interventions" && (interventions.length === 0 ? <Empty text="No interventions yet." /> : (
          <Table head={["When", "Who", "What", "Details", "Result"]}>
            {interventions.map((i) => (
              <tr key={i.id} className="border-t border-slate-100 align-top">
                <td className="whitespace-nowrap px-2 py-1.5">{when(i.created_at)}</td>
                <td className="px-2">@{i.username ?? "unknown"}</td>
                <td className="px-2">{INTERVENTION_LABELS[i.type]}</td>
                <td className="max-w-md break-words px-2">{i.type === "CHANGE_SOURCE" ? `${i.target} → ${i.content}` : (i.content ?? i.target ?? "")}</td>
                <td className="px-2 text-slate-500">{i.result}</td>
              </tr>
            ))}
          </Table>
        ))}

        {tab === "conflicts" && (conflicts.length === 0 ? <Empty text="No conflicts have occurred." /> : (
          <Table head={["Detected", "Instruction A", "Instruction B", "Rule", "Outcome"]}>
            {conflicts.map((c) => (
              <tr key={c.id} className="border-t border-slate-100 align-top">
                <td className="whitespace-nowrap px-2 py-1.5">{when(c.created_at)}</td>
                <td className="px-2">{c.constraint_a.description}<br /><span className="text-xs text-slate-500">@{c.constraint_a.created_by_username}</span></td>
                <td className="px-2">{c.constraint_b.description}<br /><span className="text-xs text-slate-500">@{c.constraint_b.created_by_username}</span></td>
                <td className="max-w-xs px-2 text-slate-600">{c.rule_applied}</td>
                <td className="px-2">{c.status === "OPEN" ? <strong className="text-red-700">open</strong>
                  : `${c.resolution?.toLowerCase().replace(/_/g, " ")}${c.resolved_by_username ? ` by @${c.resolved_by_username}` : ""}`}</td>
              </tr>
            ))}
          </Table>
        ))}

        {tab === "documents" && (
          <div className="space-y-6">
            <div>
              <h2 className="mb-2 font-semibold">Uploaded documents</h2>
              {documents.length === 0 ? <Empty text="No documents were uploaded." /> : (
                <Table head={["Title", "Source", "Type", "Status", "Chunks", "Uploaded by"]}>
                  {documents.map((d) => (
                    <tr key={d.id} className="border-t border-slate-100">
                      <td className="px-2 py-1.5 font-medium">{d.title}</td><td className="px-2">{d.source_name}</td>
                      <td className="px-2">{d.source_type}</td><td className="px-2">{d.status.toLowerCase()}</td>
                      <td className="px-2">{d.chunk_count}</td><td className="px-2">@{d.uploaded_by_username}</td>
                    </tr>
                  ))}
                </Table>
              )}
            </div>
            <div>
              <h2 className="mb-2 font-semibold">Source log (everything the agent used or rejected)</h2>
              {sources.length === 0 ? <Empty text="No sources recorded." /> : (
                <Table head={["Step", "Source", "Publisher", "Origin", "Status", "Rejected by", "Score"]}>
                  {sources.map((s) => (
                    <tr key={s.id} className="border-t border-slate-100">
                      <td className="px-2 py-1.5">{s.step_index}</td><td className="px-2">{s.title}</td><td className="px-2">{s.publisher}</td>
                      <td className="px-2">{s.origin.toLowerCase()}</td>
                      <td className={`px-2 font-medium ${s.status === "REJECTED" ? "text-red-700" : "text-emerald-700"}`}>{s.status.toLowerCase()}</td>
                      <td className="px-2">{s.rejected_by ?? ""}</td><td className="px-2">{s.score ?? ""}</td>
                    </tr>
                  ))}
                </Table>
              )}
            </div>
          </div>
        )}

        {tab === "tools" && (tools.length === 0 ? <Empty text="The agent has not used any tools." /> : (
          <Table head={["When", "Step", "Tool", "Status", "Time", "Sources", "Detail"]}>
            {tools.map((t) => (
              <tr key={t.id} className="border-t border-slate-100 align-top">
                <td className="whitespace-nowrap px-2 py-1.5">{when(t.created_at)}</td><td className="px-2">{t.step_index}</td>
                <td className="px-2 font-medium">{t.tool_name}{t.simulated && <span className="ml-1 text-[10px] font-semibold uppercase text-amber-700">simulated</span>}</td>
                <td className={`px-2 ${t.status === "SUCCESS" ? "text-emerald-700" : "font-semibold text-red-700"}`}>{t.status.toLowerCase()}</td>
                <td className="px-2">{t.duration_ms} ms</td><td className="px-2">{t.sources_count} used, {t.rejected_count} rejected</td>
                <td className="max-w-xs break-words px-2 font-mono text-xs text-slate-500">{t.error ?? JSON.stringify(t.arguments).slice(0, 120)}</td>
              </tr>
            ))}
          </Table>
        ))}

        {tab === "danger" && (
          <div className="space-y-3">
            <h2 className="font-semibold text-red-700">Delete this session</h2>
            <p className="text-sm text-slate-600">
              Permanently deletes the session, its history, constraints, memory, documents (including the files on the server),
              reports and analytics for <strong>everyone</strong>. This cannot be undone.
            </p>
            {!armed ? (
              <button className="btn-secondary !text-red-700" onClick={() => setArmed(true)}>I want to delete this session</button>
            ) : (
              <div className="flex gap-2">
                <button className="btn-primary !bg-red-600 hover:!bg-red-700" disabled={deleting} onClick={remove}>
                  {deleting && <Loader2 className="h-4 w-4 animate-spin" />} Yes, delete everything
                </button>
                <button className="btn-secondary" onClick={() => setArmed(false)}>Cancel</button>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
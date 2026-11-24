import { useCallback, useEffect, useState } from "react";
import { Code2, Copy, Download, RefreshCw, Save, Sparkles } from "lucide-react";
import { codeService } from "../services/codeService";
import type { CodeArtifact, CodeFile, CodeVersion, CodeReview } from "../services/codeService";
import { getErrorMessage } from "../services/api";

export default function SourceCodePanel({ sessionId, canEdit, canApprove = false, onNewVersion }: {
  sessionId: string; canEdit: boolean; canApprove?: boolean; onNewVersion?: number;
}) {
  const [files, setFiles] = useState<CodeArtifact[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [file, setFile] = useState<CodeFile | null>(null);
  const [versions, setVersions] = useState<CodeVersion[]>([]);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const [instruction, setInstruction] = useState("");
  const [generating, setGenerating] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [taskType, setTaskType] = useState("RESEARCH");
  const [review, setReview] = useState<CodeReview | null>(null);
  const [feedback, setFeedback] = useState("");

  const refresh = useCallback(async () => {
    try {
      const data = await codeService.list(sessionId);
      setFiles(data.files); setTaskType(data.task_type); setGenerating(data.generating);
      const nextReview = await codeService.review(sessionId);
      setReview(nextReview);
      setSelected(prev => prev && data.files.some(f => f.id === prev) ? prev : (data.files[0]?.id ?? null));
    } catch (e) { setError(getErrorMessage(e)); }
  }, [sessionId]);

  useEffect(() => { refresh(); }, [refresh, onNewVersion]);
  useEffect(() => {
    if (!selected) { setFile(null); setVersions([]); return; }
    codeService.file(sessionId, selected).then(f => { setFile(f); setDraft(f.content); setEditing(false); }).catch(e => setError(getErrorMessage(e)));
    codeService.versions(sessionId, selected).then(setVersions).catch(() => undefined);
  }, [sessionId, selected, onNewVersion]);
  useEffect(() => {
    // Poll even before the first "generating" flag is received. The automatic
    // job may begin after the panel mounts and the WebSocket event may be missed.
    const timer = window.setInterval(refresh, 4000);
    return () => window.clearInterval(timer);
  }, [refresh]);

  const run = async () => {
    setError(null); setBusy(true);
    try { await codeService.generate(sessionId, instruction); setGenerating(true); setInstruction(""); }
    catch (e) { setError(getErrorMessage(e)); }
    finally { setBusy(false); }
  };
  const reviewAction = async (approve: boolean) => {
    setBusy(true); setError(null);
    try {
      await codeService.decideReview(sessionId, approve, feedback);
      if (approve) setFeedback("");
      await refresh();
    } catch (e) { setError(getErrorMessage(e)); }
    finally { setBusy(false); }
  };
  const requestReview = async () => {
    setBusy(true); setError(null);
    try { await codeService.requestReview(sessionId); await refresh(); }
    catch (e) { setError(getErrorMessage(e)); }
    finally { setBusy(false); }
  };

  const save = async () => {
    if (!file) return;
    setBusy(true); setError(null);
    try { await codeService.update(sessionId, file.id, draft, file.version); setEditing(false); await refresh();
      const newest = await codeService.file(sessionId, file.id); setFile(newest); setDraft(newest.content);
      setVersions(await codeService.versions(sessionId, file.id));
    } catch (e) { setError(getErrorMessage(e)); }
    finally { setBusy(false); }
  };

  return <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm space-y-4">
    <div className="flex flex-wrap items-center justify-between gap-2">
      <div><h2 className="flex items-center gap-2 font-semibold"><Code2 className="h-5 w-5" /> Source Code</h2>
        <p className="text-xs text-slate-500">Files saved for everyone on your team · Version history available</p></div>
      <div className="flex gap-2 flex-wrap">
        <button className="btn-secondary" onClick={refresh}><RefreshCw className="h-4 w-4" /> Refresh</button>
        <button className="btn-secondary" disabled={!files.length} onClick={() => codeService.downloadZip(sessionId).catch(e => setError(getErrorMessage(e)))}><Download className="h-4 w-4" /> Source ZIP</button>
        <button className="btn-secondary" disabled={!files.length} onClick={() => codeService.downloadZip(sessionId, true).catch(e => setError(getErrorMessage(e)))}><Download className="h-4 w-4" /> Project ZIP</button>
      </div>
    </div>
    {error && <div role="alert" className="rounded-lg bg-red-50 p-2 text-sm text-red-700">{error}</div>}
    {taskType !== "RESEARCH" && files.length > 0 && <div className="space-y-3 rounded-xl border border-amber-200 bg-amber-50 p-4" aria-label="Code review">
      <h3 className="font-semibold">Review your team's work</h3>
      {review?.status === "PENDING" ? <>
        <p className="text-sm">Source code is awaiting owner approval. Check the generated files and their validation status first. Approval does not mean the code has been compiled or tested.</p>
        {canApprove ? <div className="space-y-2">
          <button className="btn-primary" disabled={busy || generating} onClick={() => reviewAction(true)}>Approve code and finalize report</button>
          <label htmlFor="code-review-feedback" className="block text-xs">Changes required (required for rejection)</label>
          <textarea id="code-review-feedback" className="input min-h-20" value={feedback} onChange={e => setFeedback(e.target.value)} placeholder="Describe what the AI should change..." />
          <button className="btn-secondary" disabled={busy || generating || feedback.trim().length < 3} onClick={() => reviewAction(false)}>Request changes</button>
        </div> : <p className="text-xs">The session owner must approve or request changes.</p>}
      </> : <>
        <p className="text-sm">Review: <strong>{review?.status === "NONE" || !review ? "Not requested yet" : review.status === "REJECTED" ? "Changes requested" : review.status === "APPROVED" ? "Approved" : review.status === "EXPIRED" ? "Needs a new review" : review.status}</strong>{review?.note ? ` · ${review.note}` : ""}</p>
        {review?.status === "APPROVED" && <p className="text-xs">The approved code versions are included in the finalized report. Editing files requires a new approval.</p>}
        {canEdit && !generating && review?.status !== "APPROVED" && <button className="btn-secondary" disabled={busy} onClick={requestReview}>Request team review</button>}
      </>}
    </div>}
    {canEdit && taskType !== "RESEARCH" && <div className="space-y-2 rounded-xl bg-slate-50 p-3">
      <label htmlFor="code-instruction" className="block text-sm font-medium">Ask the AI to improve your code</label>
      <p className="text-xs text-slate-600">Describe the change in your own words. Your current files and past versions remain saved.</p>
      <textarea id="code-instruction" className="input min-h-20" value={instruction} onChange={e => setInstruction(e.target.value)} placeholder="Optional changes, e.g. Add division-by-zero handling" />
      <button className="btn-primary" disabled={busy || generating} onClick={run}><Sparkles className="h-4 w-4" /> {generating ? "Working on files..." : files.length ? "Ask AI to make changes" : "Create project files"}</button>
      {generating && <p role="status" className="text-xs text-amber-700">Your AI teammate is preparing files. You'll see each file as soon as it's saved.</p>}
    </div>}
    {!files.length ? <p className="text-sm text-slate-500">{taskType === "RESEARCH" ? "This is a research-only session; no source code was requested." : "No source code saved yet. Coding requests generate files automatically when the session starts; generation can take time, or you can retry above."}</p> :
      <div className="grid gap-3 md:grid-cols-[minmax(160px,1fr)_minmax(0,3fr)]">
        <nav aria-label="Project files" className="max-h-96 overflow-y-auto rounded-lg border border-slate-200 p-2">
          {files.map(f => <button key={f.id} onClick={() => setSelected(f.id)} className={`block w-full truncate rounded px-2 py-2 text-left text-xs ${selected === f.id ? "bg-brand-50 font-semibold text-brand-700" : "hover:bg-slate-50"}`} title={f.path}>{f.path} · v{f.version}</button>)}
        </nav>
        <div className="min-w-0 space-y-2">
          {file && <>
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="min-w-0"><p className="truncate text-sm font-semibold">{file.path}</p><p className="text-xs text-slate-500">{file.language} · {file.validation_status}</p></div>
              <div className="flex gap-1 flex-wrap">
                <button className="btn-secondary !px-2" onClick={() => navigator.clipboard.writeText(file.content)} title="Copy"><Copy className="h-4 w-4" /></button>
                <button className="btn-secondary !px-2" onClick={() => codeService.downloadFile(sessionId, file.id, file.path.split("/").pop() || "code.txt").catch(e => setError(getErrorMessage(e)))} title="Download"><Download className="h-4 w-4" /></button>
                {canEdit && files.find(f => f.id === file.id)?.version === file.version && <button className="btn-secondary" onClick={() => { setEditing(!editing); setDraft(file.content); }}>{editing ? "Cancel" : "Edit"}</button>}
                {editing && <button className="btn-primary" disabled={busy} onClick={save}><Save className="h-4 w-4" /> Save</button>}
              </div>
            </div>
            <label className="text-xs text-slate-500" htmlFor="code-version">Version: </label>
            <select id="code-version" value={file.version} onChange={e => codeService.file(sessionId, file.id, Number(e.target.value)).then(f => { setFile(f); setDraft(f.content); setEditing(false); }).catch(e => setError(getErrorMessage(e)))} className="rounded border p-1 text-xs">
              {versions.map(v => <option key={v.version} value={v.version}>v{v.version} ({v.origin})</option>)}
            </select>
            {editing ? <textarea className="w-full min-h-80 rounded-lg border p-3 font-mono text-xs" spellCheck={false} value={draft} onChange={e => setDraft(e.target.value)} /> :
              <pre className="max-h-[540px] overflow-auto whitespace-pre rounded-lg bg-slate-900 p-4 text-xs text-slate-100"><code>{file.content}</code></pre>}
            <p className="text-xs text-slate-500">{file.validation_details}</p>
          </>}
        </div>
      </div>}
  </div>;
}

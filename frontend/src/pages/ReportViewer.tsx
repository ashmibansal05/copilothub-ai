import { ArrowLeft, Download, Loader2, RefreshCw } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import axios from "axios";
import { getErrorMessage } from "../services/api";
import { sessionService } from "../services/sessionService";
import { codeService } from "../services/codeService";
import ReportBody from "../components/ReportBody";
import type { ReportDetail } from "../types";

export default function ReportViewer() {
  const { id } = useParams<{ id: string }>();
  const [report, setReport] = useState<ReportDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [taskType, setTaskType] = useState("RESEARCH");
  const [reviewStatus, setReviewStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!id) return;
    try {
      const details = await codeService.list(id);
      setTaskType(details.task_type);
      if (details.task_type !== "RESEARCH") {
        const review = await codeService.review(id);
        setReviewStatus(review.status);
      }
      try {
        setReport(await sessionService.finalReport(id));
      } catch (finalError) {
        if (!axios.isAxiosError(finalError) || finalError.response?.status !== 404) throw finalError;
        const summaries = await sessionService.reports(id);
        const draft = [...summaries].reverse().find(r => r.kind === "DRAFT");
        setReport(draft ? await sessionService.report(id, draft.id) : null);
      }
      setError(null);
    } catch (err) {
      if (axios.isAxiosError(err) && err.response?.status === 404) setReport(null);
      else setError(getErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => { load(); }, [load]);

  const generate = async () => {
    if (!id) return;
    setError(null);
    setGenerating(true);
    const before = report?.id;
    try {
      await sessionService.generateReport(id);
      for (let i = 0; i < 60; i++) { // poll until a NEW report appears (up to ~2 minutes)
        await new Promise((r) => setTimeout(r, 2000));
        try {
          const latest = await sessionService.finalReport(id);
          if (latest.id !== before) { setReport(latest); break; }
        } catch { /* not there yet */ }
      }
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setGenerating(false);
    }
  };

  const refreshApproved = async () => {
    if (!id) return;
    setError(null); setRefreshing(true);
    try {
      await codeService.refreshApprovedReport(id);
      await load();
    } catch (err) { setError(getErrorMessage(err)); }
    finally { setRefreshing(false); }
  };

  const download = async (format: "md" | "html" | "docx") => {
    if (!id || !report) return;
    try { await sessionService.downloadReport(id, report.id, format); }
    catch (err) { setError(getErrorMessage(err)); }
  };

  if (loading) {
    return <div className="flex justify-center py-20"><Loader2 className="h-8 w-8 animate-spin text-brand-600" aria-label="Loading" /></div>;
  }

  return (
    <div className="mx-auto max-w-3xl space-y-4">
      <Link to={`/sessions/${id}`} className="inline-flex items-center gap-1 text-sm text-slate-600 hover:text-slate-900">
        <ArrowLeft className="h-4 w-4" /> Back to the session
      </Link>

      {error && <div role="alert" className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div>}

      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-2xl font-bold">{report?.title ?? "Project report"}</h1>
        <div className="flex flex-wrap gap-2">
          {taskType === "RESEARCH" && <button className="btn-secondary" onClick={generate} disabled={generating}>
            {generating ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
            {report ? "Regenerate" : "Generate report"}
          </button>}
          {report && report.kind === "FINAL" && taskType !== "RESEARCH" && reviewStatus === "APPROVED" && <button className="btn-secondary" disabled={refreshing} onClick={refreshApproved}>
            <RefreshCw className="h-4 w-4" /> {refreshing ? "Preparing..." : "Improve report from approved files"}
          </button>}
          {report && report.kind === "FINAL" && taskType !== "RESEARCH" && <button className="btn-secondary" onClick={() => codeService.downloadZip(id!, true).catch(e => setError(getErrorMessage(e)))}><Download className="h-4 w-4" /> Complete Project</button>}
          {report && (["md", "html", "docx"] as const).map((f) => (
            <button key={f} className="btn-secondary" onClick={() => download(f)}>
              <Download className="h-4 w-4" /> {f === "md" ? "Markdown" : f === "html" ? "HTML" : "Word"}
            </button>
          ))}
        </div>
      </div>

      {!report ? (
        <div className="rounded-2xl border border-dashed border-slate-300 bg-white p-10 text-center">
          <h2 className="font-semibold">No final report yet</h2>
          <p className="mt-1 text-sm text-slate-500">
            {taskType !== "RESEARCH" ? `Code review status: ${reviewStatus ?? "not requested"}. The final project report is created after the owner approves the generated source code. Return to Source Code to review.` : "It is created automatically when the research agent finishes or you can generate a draft."}
          </p>
        </div>
      ) : (
        <>
          <div className={`rounded-xl border p-4 text-sm ${report.kind === "DRAFT" ? "border-amber-200 bg-amber-50 text-amber-900" : "border-green-200 bg-green-50 text-green-900"}`}>
            {report.kind === "DRAFT" ? "Working report — this is a draft. Review and approve the project files to finalize it." : "Final report — this version is saved as a completed deliverable."}
          </div>
          <p className="text-xs text-slate-500">
            Generated {new Date(report.created_at).toLocaleString()}
            {report.engine && <> · engine: {report.engine}</>}. Facts come from the session records; only the
            summary, findings, comparison and conclusion are written by the agent: check them against the evidence.
          </p>
          {(report.sections ?? []).map((s, n) => (
            <section key={s.key} className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
              <h2 className="mb-3 text-lg font-semibold">{n + 1}. {s.title}</h2>
              <ReportBody body={s.body} />
            </section>
          ))}
        </>
      )}
    </div>
  );
}
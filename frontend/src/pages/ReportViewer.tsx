import { ArrowLeft, Download, Loader2, RefreshCw } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import axios from "axios";
import { getErrorMessage } from "../services/api";
import { sessionService } from "../services/sessionService";
import type { ReportDetail } from "../types";

export default function ReportViewer() {
  const { id } = useParams<{ id: string }>();
  const [report, setReport] = useState<ReportDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!id) return;
    try {
      setReport(await sessionService.finalReport(id));
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
        <h1 className="text-2xl font-bold">{report?.title ?? "Final report"}</h1>
        <div className="flex flex-wrap gap-2">
          <button className="btn-secondary" onClick={generate} disabled={generating}>
            {generating ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
            {report ? "Regenerate" : "Generate report"}
          </button>
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
            It is created automatically when the agent finishes, or you can generate one from what has been done so far.
          </p>
        </div>
      ) : (
        <>
          <p className="text-xs text-slate-500">
            Generated {new Date(report.created_at).toLocaleString()}
            {report.engine && <> · engine: {report.engine}</>}. Facts come from the session records; only the
            summary, findings, comparison and conclusion are written by the agent: check them against the evidence.
          </p>
          {(report.sections ?? []).map((s, n) => (
            <section key={s.key} className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
              <h2 className="mb-3 text-lg font-semibold">{n + 1}. {s.title}</h2>
              {/* Plain text on purpose: report content is never interpreted as HTML */}
              <div className="whitespace-pre-wrap break-words text-sm leading-relaxed text-slate-800">{s.body}</div>
            </section>
          ))}
        </>
      )}
    </div>
  );
}
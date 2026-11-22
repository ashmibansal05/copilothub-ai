import { AlertTriangle, Ban, CheckCircle2, FileText, Wrench } from "lucide-react";
import type { SessionEvent } from "../types";

interface Source {
  title: string;
  publisher: string;
  source_type?: string;
  preferred?: boolean;
  rejected_by?: string;
}

export default function ToolActivity({
  events,
  onRejectSource,
}: {
  events: SessionEvent[];
  onRejectSource?: (publisher: string) => void;
}) {
  const calls = events.filter((e) => e.type === "TOOL_COMPLETED");

  const seen = new Set<string>();
  const rejectedSeen = new Set<string>();
  const sources: (Source & { simulated: boolean })[] = [];
  const rejected: Source[] = [];
  for (const e of calls) {
    for (const s of (e.payload.sources ?? []) as Source[]) {
      const key = `${s.title}|${s.publisher}`;
      if (!seen.has(key)) {
        seen.add(key);
        sources.push({ ...s, simulated: Boolean(e.payload.simulated) });
      }
    }
    for (const s of (e.payload.rejected_sources ?? []) as Source[]) {
      const key = `${s.title}|${s.publisher}`;
      if (!rejectedSeen.has(key)) {
        rejectedSeen.add(key);
        rejected.push(s);
      }
    }
  }

  return (
    <div className="grid gap-4 md:grid-cols-2">
      <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <h2 className="mb-3 flex items-center gap-2 font-semibold">
          <Wrench className="h-4 w-4 text-slate-500" /> Tool activity
        </h2>
        {calls.length === 0 ? (
          <p className="text-sm text-slate-500">No tool calls yet.</p>
        ) : (
          <ul className="max-h-64 space-y-2 overflow-y-auto pr-1">
            {[...calls].reverse().map((e) => (
              <li key={e.id} className="rounded-lg bg-slate-50 px-3 py-2 text-sm">
                <div className="flex items-center justify-between gap-2">
                  <span className="flex items-center gap-1.5 font-medium">
                    {e.payload.success ? (
                      <CheckCircle2 className="h-4 w-4 text-emerald-600" aria-label="Succeeded" />
                    ) : (
                      <AlertTriangle className="h-4 w-4 text-red-600" aria-label="Failed" />
                    )}
                    {e.payload.tool}
                  </span>
                  <span className="text-xs text-slate-400">{e.payload.duration_ms} ms</span>
                </div>
                {e.payload.simulated && (
                  <span className="mt-1 inline-block rounded bg-amber-100 px-1.5 py-0.5 text-[10px] font-semibold uppercase text-amber-800">
                    simulated
                  </span>
                )}
                {(e.payload.rejected_sources?.length ?? 0) > 0 && (
                  <span className="ml-1 inline-block rounded bg-red-100 px-1.5 py-0.5 text-[10px] font-semibold uppercase text-red-700">
                    {e.payload.rejected_sources.length} filtered
                  </span>
                )}
                {e.payload.error && <p className="mt-1 text-xs text-red-700">{String(e.payload.error)}</p>}
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <h2 className="mb-3 flex items-center gap-2 font-semibold">
          <FileText className="h-4 w-4 text-slate-500" /> Retrieved sources
        </h2>
        {sources.length === 0 && rejected.length === 0 ? (
          <p className="text-sm text-slate-500">No sources yet.</p>
        ) : (
          <ul className="max-h-64 space-y-2 overflow-y-auto pr-1">
            {sources.map((s) => (
              <li key={`${s.title}|${s.publisher}`} className="rounded-lg bg-slate-50 px-3 py-2 text-sm">
                <div className="flex items-start justify-between gap-2">
                  <p className="font-medium">{s.title}</p>
                  {onRejectSource && (
                    <button onClick={() => onRejectSource(s.publisher)}
                      className="shrink-0 rounded border border-slate-300 px-1.5 py-0.5 text-xs text-slate-600 hover:border-red-400 hover:text-red-700"
                      aria-label={`Reject source ${s.publisher}`}>
                      Reject
                    </button>
                  )}
                </div>
                <p className="text-xs text-slate-500">
                  {s.publisher}
                  {s.preferred && <span className="ml-2 font-semibold uppercase text-emerald-700">preferred</span>}
                  {s.simulated && <span className="ml-2 font-semibold uppercase text-amber-700">simulated</span>}
                </p>
              </li>
            ))}
            {rejected.map((s) => (
              <li key={`r|${s.title}|${s.publisher}`} className="rounded-lg bg-red-50 px-3 py-2 text-sm">
                <p className="flex items-center gap-1.5 font-medium text-red-800 line-through">
                  <Ban className="h-3.5 w-3.5 shrink-0 no-underline" aria-hidden /> {s.title}
                </p>
                <p className="text-xs text-red-700">
                  {s.publisher} · filtered by constraint “{s.rejected_by}”
                </p>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
import { AlertTriangle, CheckCircle2, FileText, Wrench } from "lucide-react";
import type { SessionEvent } from "../types";

export default function ToolActivity({ events }: { events: SessionEvent[] }) {
  const calls = events.filter((e) => e.type === "TOOL_COMPLETED");

  // Unique sources across all tool calls
  const seen = new Set<string>();
  const sources: { title: string; publisher: string; simulated: boolean }[] = [];
  for (const e of calls) {
    for (const s of (e.payload.sources ?? []) as { title: string; publisher: string }[]) {
      const key = `${s.title}|${s.publisher}`;
      if (!seen.has(key)) {
        seen.add(key);
        sources.push({ ...s, simulated: Boolean(e.payload.simulated) });
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
        {sources.length === 0 ? (
          <p className="text-sm text-slate-500">No sources yet.</p>
        ) : (
          <ul className="max-h-64 space-y-2 overflow-y-auto pr-1">
            {sources.map((s) => (
              <li key={`${s.title}|${s.publisher}`} className="rounded-lg bg-slate-50 px-3 py-2 text-sm">
                <p className="font-medium">{s.title}</p>
                <p className="text-xs text-slate-500">
                  {s.publisher}
                  {s.simulated && <span className="ml-2 font-semibold uppercase text-amber-700">simulated</span>}
                </p>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
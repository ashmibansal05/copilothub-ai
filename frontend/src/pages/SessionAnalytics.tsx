import { ArrowLeft, Loader2 } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  Bar, BarChart, CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { getErrorMessage } from "../services/api";
import { sessionService } from "../services/sessionService";
import type { SessionAnalytics as Analytics } from "../types";

const pct = (v: number | null | undefined) => (v == null ? "–" : `${Math.round(v * 100)}%`);
const dur = (v: number | null | undefined) => (v == null ? "–" : v < 90 ? `${Math.round(v)} s` : `${(v / 60).toFixed(1)} min`);

function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <h2 className="mb-3 font-semibold">{title}</h2>
      {children}
    </div>
  );
}

export default function SessionAnalytics() {
  const { id } = useParams<{ id: string }>();
  const [a, setA] = useState<Analytics | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (id) sessionService.sessionAnalytics(id).then(setA).catch((e) => setError(getErrorMessage(e)));
  }, [id]);

  if (error) return <div role="alert" className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div>;
  if (!a) return <div className="flex justify-center py-20"><Loader2 className="h-8 w-8 animate-spin text-brand-600" aria-label="Loading" /></div>;

  const byStep = new Map<number, { step: number; confidence?: number; risk?: number }>();
  a.confidence_series.forEach((c) => byStep.set(c.step_index, { step: c.step_index, confidence: Math.round(c.confidence * 100) }));
  a.risk.history.forEach((r) => byStep.set(r.step_index, { ...(byStep.get(r.step_index) ?? { step: r.step_index }), risk: Math.round(r.probability * 100) }));
  const series = [...byStep.values()].sort((x, y) => x.step - y.step);
  const types = Object.entries(a.interventions_by_type).map(([name, count]) => ({ name: name.replace(/_/g, " ").toLowerCase(), count }));

  const facts: [string, string][] = [
    ["Status", a.status.toLowerCase()], ["Engine", a.engine ?? "–"], ["Duration", dur(a.duration_seconds)],
    ["Steps", `${a.steps_completed} of ${a.steps_planned}`], ["Final confidence", pct(a.final_confidence)],
    ["Interventions", `${a.interventions_total} (${a.corrective} corrective, ${a.comments} comments)`],
    ["Tool calls", `${a.tool_calls} (${a.tool_failures} failed or rejected)`],
    ["Retries / failed attempts", `${a.failed_attempts}${a.recovered ? " (recovered)" : ""}`],
    ["Approvals", `${a.approvals_approved} approved, ${a.approvals_rejected} rejected`],
    ["Conflicts", `${a.conflicts_total} (${a.conflicts_open} open)`],
    ["Sources", `${a.sources_used} used, ${a.sources_rejected} rejected (${pct(a.source_rejection_rate)})`],
    ["Documents", String(a.documents)],
  ];

  return (
    <div className="space-y-4">
      <Link to={`/sessions/${id}`} className="inline-flex items-center gap-1 text-sm text-slate-600 hover:text-slate-900">
        <ArrowLeft className="h-4 w-4" /> Back to the session
      </Link>
      <h1 className="text-2xl font-bold">{a.name}: analytics</h1>

      <Card title="Summary">
        <dl className="grid gap-x-6 gap-y-2 text-sm sm:grid-cols-2 lg:grid-cols-3">
          {facts.map(([k, v]) => (
            <div key={k}><dt className="text-xs text-slate-500">{k}</dt><dd className="font-medium">{v}</dd></div>
          ))}
        </dl>
      </Card>

      <Card title="Confidence and predicted intervention risk, by step">
        {series.length === 0 ? <p className="py-6 text-center text-sm text-slate-500">No completed steps yet.</p> : (
          <>
            <ResponsiveContainer width="100%" height={260}>
              <LineChart data={series}>
                <CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="step" label={{ value: "step", position: "insideBottom", offset: -2 }} />
                <YAxis domain={[0, 100]} unit="%" /><Tooltip /><Legend />
                <Line type="monotone" dataKey="confidence" name="Agent confidence" stroke="#10b981" strokeWidth={2} />
                <Line type="monotone" dataKey="risk" name="Predicted risk" stroke="#ef4444" strokeWidth={2} strokeDasharray="5 4" />
              </LineChart>
            </ResponsiveContainer>
            {a.risk.n > 0 && (
              <p className="mt-2 text-xs text-slate-500">
                Risk model data source: <strong>{a.risk.data_source}</strong>. Mean risk before an intervention:{" "}
                {pct(a.risk.mean_when_intervened)}, otherwise {pct(a.risk.mean_when_not)} ({a.risk.observed_n} steps with known outcome).
              </p>
            )}
          </>
        )}
      </Card>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="Interventions by type">
          {types.length === 0 ? <p className="py-6 text-center text-sm text-slate-500">None.</p> : (
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={types} layout="vertical" margin={{ left: 40 }}>
                <CartesianGrid strokeDasharray="3 3" /><XAxis type="number" allowDecimals={false} />
                <YAxis type="category" dataKey="name" width={120} tick={{ fontSize: 12 }} />
                <Tooltip /><Bar dataKey="count" fill="#4f46e5" />
              </BarChart>
            </ResponsiveContainer>
          )}
        </Card>
        <Card title="Tools">
          {a.tools.length === 0 ? <p className="py-6 text-center text-sm text-slate-500">No tool calls.</p> : (
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={a.tools}>
                <CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="tool" tick={{ fontSize: 11 }} />
                <YAxis allowDecimals={false} /><Tooltip /><Legend />
                <Bar dataKey="calls" fill="#4f46e5" /><Bar dataKey="failures" fill="#ef4444" />
              </BarChart>
            </ResponsiveContainer>
          )}
        </Card>
      </div>
    </div>
  );
}
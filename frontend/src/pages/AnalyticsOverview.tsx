import { Loader2 } from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  Bar, BarChart, CartesianGrid, Cell, Legend, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { getErrorMessage } from "../services/api";
import { sessionService } from "../services/sessionService";
import type { AnalyticsOverview as Overview, MLStatus } from "../types";

const pct = (v: number | null | undefined) => (v == null ? "–" : `${Math.round(v * 100)}%`);
const dur = (v: number | null | undefined) => (v == null ? "–" : v < 90 ? `${Math.round(v)} s` : `${(v / 60).toFixed(1)} min`);
const num = (v: number | null | undefined, d = 2) => (v == null ? "–" : v.toFixed(d));
const COLORS = ["#4f46e5", "#10b981", "#ef4444", "#94a3b8", "#f59e0b"];

function Stat({ label, value, hint }: { label: string; value: string | number; hint?: string }) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
      <p className="text-xs text-slate-500">{label}</p>
      <p className="mt-1 text-2xl font-bold">{value}</p>
      {hint && <p className="mt-0.5 text-xs text-slate-400">{hint}</p>}
    </div>
  );
}

function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <h2 className="mb-3 font-semibold">{title}</h2>
      {children}
    </div>
  );
}

const Empty = () => <p className="py-8 text-center text-sm text-slate-500">No data yet.</p>;

export default function AnalyticsOverview() {
  const [data, setData] = useState<Overview | null>(null);
  const [ml, setMl] = useState<MLStatus | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    sessionService.analyticsOverview().then(setData).catch((e) => setError(getErrorMessage(e)));
    sessionService.mlStatus().then(setMl).catch(() => undefined);
  }, []);

  if (error) return <div role="alert" className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div>;
  if (!data) return <div className="flex justify-center py-20"><Loader2 className="h-8 w-8 animate-spin text-brand-600" aria-label="Loading" /></div>;

  const types = Object.entries(data.interventions_by_type).map(([name, count]) => ({ name: name.replace(/_/g, " ").toLowerCase(), count }));
  const statuses = [
    { name: "Completed", value: data.sessions_completed }, { name: "Failed", value: data.sessions_failed },
    { name: "Cancelled", value: data.sessions_cancelled }, { name: "Active", value: data.sessions_active },
  ].filter((s) => s.value > 0);
  const models = ml?.available
    ? Object.entries(ml.models).map(([name, m]) => ({
        name: name.replace(/_/g, " "), "ROC-AUC": +m.test.roc_auc.toFixed(3), "F1": +m.test.f1.toFixed(3),
      }))
    : [];
  const p = data.prediction;
  const r = data.research;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Analytics</h1>
        <p className="text-slate-600">Computed from your stored sessions. Nothing here is estimated or invented.</p>
      </div>

      <div className="grid grid-cols-2 gap-4 md:grid-cols-4 lg:grid-cols-5">
        <Stat label="Sessions" value={data.sessions_total} hint={`${data.sessions_active} active`} />
        <Stat label="Completed" value={data.sessions_completed} hint={`${data.sessions_failed} failed · ${data.sessions_cancelled} cancelled`} />
        <Stat label="Agent success rate" value={pct(data.success_rate)} hint="completed / finished" />
        <Stat label="Avg duration" value={dur(data.avg_duration_seconds)} />
        <Stat label="Human interventions" value={data.interventions_total} hint={`${data.interventions_corrective} corrective`} />
        <Stat label="Avg confidence" value={pct(data.avg_confidence)} hint={`final: ${pct(data.avg_final_confidence)}`} />
        <Stat label="Tool failure rate" value={pct(data.tool_failure_rate)} hint={`${data.tool_failures} of ${data.tool_calls} calls`} />
        <Stat label="Approval rate" value={pct(data.approval_rate)} hint={`${data.approvals_approved} approved · ${data.approvals_rejected} rejected`} />
        <Stat label="Conflicts" value={data.conflicts_total} hint={`${data.conflicts_open} open`} />
        <Stat label="Source rejection rate" value={pct(data.source_rejection_rate)} hint={`${data.sources_rejected} of ${data.sources_used + data.sources_rejected}`} />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="Interventions by type">
          {types.length === 0 ? <Empty /> : (
            <ResponsiveContainer width="100%" height={260}>
              <BarChart data={types} layout="vertical" margin={{ left: 40 }}>
                <CartesianGrid strokeDasharray="3 3" /><XAxis type="number" allowDecimals={false} />
                <YAxis type="category" dataKey="name" width={120} tick={{ fontSize: 12 }} />
                <Tooltip /><Bar dataKey="count" fill="#4f46e5" />
              </BarChart>
            </ResponsiveContainer>
          )}
        </Card>
        <Card title="Sessions by outcome">
          {statuses.length === 0 ? <Empty /> : (
            <ResponsiveContainer width="100%" height={260}>
              <PieChart>
                <Pie data={statuses} dataKey="value" nameKey="name" outerRadius={90} label>
                  {statuses.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
                </Pie>
                <Tooltip /><Legend />
              </PieChart>
            </ResponsiveContainer>
          )}
        </Card>
        <Card title="Agent confidence (all steps)">
          {data.confidence_histogram.every((b) => b.count === 0) ? <Empty /> : (
            <ResponsiveContainer width="100%" height={240}>
              <BarChart data={data.confidence_histogram}>
                <CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="label" />
                <YAxis allowDecimals={false} /><Tooltip /><Bar dataKey="count" fill="#10b981" />
              </BarChart>
            </ResponsiveContainer>
          )}
        </Card>
        <Card title="Tool calls and failures">
          {data.tools.length === 0 ? <Empty /> : (
            <ResponsiveContainer width="100%" height={240}>
              <BarChart data={data.tools}>
                <CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="tool" tick={{ fontSize: 11 }} />
                <YAxis allowDecimals={false} /><Tooltip /><Legend />
                <Bar dataKey="calls" fill="#4f46e5" /><Bar dataKey="failures" fill="#ef4444" />
              </BarChart>
            </ResponsiveContainer>
          )}
        </Card>
      </div>

      <Card title="Intervention predictor: how it behaved on your sessions">
        {p.n === 0 ? <p className="text-sm text-slate-500">No predictions recorded yet.</p> : (
          <div className="grid gap-3 text-sm sm:grid-cols-3">
            <div><p className="text-xs text-slate-500">Predictions made</p><p className="text-xl font-bold">{p.n}</p></div>
            <div><p className="text-xs text-slate-500">Mean risk when a human then intervened</p><p className="text-xl font-bold">{pct(p.mean_when_intervened)}</p></div>
            <div><p className="text-xs text-slate-500">Mean risk when no human intervened</p><p className="text-xl font-bold">{pct(p.mean_when_not)}</p></div>
            <p className="text-xs text-slate-500 sm:col-span-3">
              Based on {p.observed_n} predictions whose outcome is known. Model data source: <strong>{p.data_source}</strong>.
              {p.data_source?.includes("synthetic") && " It was trained on synthetic data, so a gap here is the real test of whether it is useful."}
            </p>
          </div>
        )}
      </Card>

      <Card title="Predictor model comparison (held-out test set)">
        {!ml?.available ? (
          <p className="text-sm text-slate-500">No model has been trained yet. Run <code>python -m app.ml.train</code>.</p>
        ) : (
          <>
            {ml.warning && <p className="mb-3 rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-900">{ml.warning}</p>}
            <ResponsiveContainer width="100%" height={240}>
              <BarChart data={models}>
                <CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="name" /><YAxis domain={[0, 1]} />
                <Tooltip /><Legend /><Bar dataKey="ROC-AUC" fill="#4f46e5" /><Bar dataKey="F1" fill="#10b981" />
              </BarChart>
            </ResponsiveContainer>
            <p className="mt-2 text-xs text-slate-500">
              Data: {ml.data_source} · {ml.n_rows} rows ({ml.n_test} held out) · selected: <strong>{ml.selected_model?.replace(/_/g, " ")}</strong>
              {ml.baseline && <> · naive rule ({ml.baseline.rule}) scores ROC-AUC {num(ml.baseline.roc_auc, 3)}, F1 {num(ml.baseline.f1, 3)}</>}
            </p>
          </>
        )}
      </Card>

      <Card title="Research metrics (observational)">
        <div className="grid grid-cols-2 gap-3 text-sm md:grid-cols-4">
          <Stat label="Task completion rate" value={pct(r.task_completion_rate)} />
          <Stat label="Human correction rate" value={num(r.human_correction_rate)} hint="corrective interventions per step" />
          <Stat label="Incorrect actions / session" value={num(r.incorrect_actions_per_session)} hint="corrections + rejected approvals" />
          <Stat label="Agent recovery rate" value={pct(r.agent_recovery_rate)} hint="sessions that had failures but still completed" />
          <Stat label="Avg time to completion" value={dur(r.avg_time_to_completion_seconds)} />
          <Stat label="Source rejection rate" value={pct(r.source_rejection_rate)} />
          <Stat label="Tool failure rate" value={pct(r.tool_failure_rate)} />
          <Stat label="Conflicts / session" value={num(r.conflicts_per_session)} />
        </div>
        <table className="mt-4 w-full text-left text-sm">
          <thead className="text-xs text-slate-500"><tr><th className="py-1">Group</th><th>Sessions</th><th>Completion</th><th>Avg duration</th><th>Avg final confidence</th></tr></thead>
          <tbody>
            {r.groups.map((g) => (
              <tr key={g.label} className="border-t border-slate-100">
                <td className="py-1.5">{g.label}</td><td>{g.sessions}</td><td>{pct(g.completion_rate)}</td>
                <td>{dur(g.avg_duration_seconds)}</td><td>{pct(g.avg_final_confidence)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="mt-3 text-xs text-slate-500">{r.notes}</p>
      </Card>

      <Card title="Recent sessions">
        {data.recent_sessions.length === 0 ? <Empty /> : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="text-xs text-slate-500">
                <tr><th className="py-1">Session</th><th>Status</th><th>Duration</th><th>Interventions</th><th>Tool failures</th><th>Conflicts</th><th>Final confidence</th><th /></tr>
              </thead>
              <tbody>
                {data.recent_sessions.map((s) => (
                  <tr key={s.id} className="border-t border-slate-100">
                    <td className="py-1.5 font-medium">{s.name}</td><td>{s.status.toLowerCase()}</td><td>{dur(s.duration_seconds)}</td>
                    <td>{s.interventions} ({s.corrective} corrective)</td><td>{s.tool_failures}</td><td>{s.conflicts}</td>
                    <td>{pct(s.final_confidence)}</td>
                    <td><Link className="text-brand-600 hover:underline" to={`/sessions/${s.id}/analytics`}>Details</Link></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}
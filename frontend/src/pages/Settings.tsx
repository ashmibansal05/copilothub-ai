import { Loader2 } from "lucide-react";
import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext";
import { useToast } from "../contexts/ToastContext";
import { getErrorMessage, TOKEN_KEY } from "../services/api";
import { authService } from "../services/authService";
import { sessionService } from "../services/sessionService";
import type { MLStatus, NLPStatus, SystemStatus } from "../types";

function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
      <h2 className="mb-4 font-semibold">{title}</h2>
      {children}
    </section>
  );
}

const yesNo = (v: boolean) => (v ? "on" : "off");
const pct = (v: number | null | undefined) => (v == null ? "–" : `${Math.round(v * 100)}%`);

export default function Settings() {
  const { user, logout } = useAuth();
  const toast = useToast();
  const navigate = useNavigate();
  const [system, setSystem] = useState<SystemStatus | null>(null);
  const [nlp, setNlp] = useState<NLPStatus | null>(null);
  const [ml, setMl] = useState<MLStatus | null>(null);
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    sessionService.systemStatus().then(setSystem).catch(() => undefined);
    sessionService.nlpStatus().then(setNlp).catch(() => undefined);
    sessionService.mlStatus().then(setMl).catch(() => undefined);
  }, []);

  const changePassword = async (e: FormEvent) => {
    e.preventDefault();
    if (next !== confirm) return toast.error("The new passwords do not match.");
    setBusy(true);
    try {
      const token = await authService.changePassword(current, next);
      localStorage.setItem(TOKEN_KEY, token.access_token); // every OTHER device is now signed out
      setCurrent(""); setNext(""); setConfirm("");
      toast.success("Password changed. Other devices were signed out.");
    } catch (err) {
      toast.error(getErrorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  if (!user) return null;
  const rows: [string, string][] = system
    ? [
        ["Version", `${system.app_name} ${system.version} (${system.environment})`],
        ["Agent engine", system.demo_mode ? "Demo mode (simulated web results, scripted agent)" : `${system.llm.provider} / ${system.llm.model}`],
        ["Language model", system.llm.ready ? "ready" : `not ready: ${system.llm.detail}`],
        ["Embeddings", system.embedding_backend === "hashing" ? "lexical hashing (offline fallback)" : `${system.embedding_model}`],
        ["Web search", system.web_search_provider === "demo" ? "demo (simulated)" : system.web_search_provider],
        ["Agent tools", system.tools_enabled ? system.enabled_tools.join(", ") : "off (single-shot steps)"],
        ["Final approval required", yesNo(system.require_final_approval)],
        ["Free-text auto-apply", yesNo(system.nlp_auto_apply)],
        ["Risk prediction", yesNo(system.risk_prediction_enabled)],
        ["Rate limiting", yesNo(system.rate_limit_enabled)],
        ["Upload limit", `${system.max_upload_mb} MB`],
      ]
    : [];

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <h1 className="text-2xl font-bold">Settings</h1>

      <Card title="Your account">
        <dl className="grid gap-3 text-sm sm:grid-cols-2">
          <div><dt className="text-xs text-slate-500">Name</dt><dd className="font-medium">{user.full_name}</dd></div>
          <div><dt className="text-xs text-slate-500">Username</dt><dd className="font-medium">@{user.username}</dd></div>
          <div><dt className="text-xs text-slate-500">Email</dt><dd className="font-medium">{user.email}</dd></div>
          <div><dt className="text-xs text-slate-500">Member since</dt><dd className="font-medium">{new Date(user.created_at).toLocaleDateString()}</dd></div>
        </dl>
        <button className="btn-secondary mt-4" onClick={async () => { await logout(); navigate("/login", { replace: true }); }}>
          Sign out
        </button>
      </Card>

      <Card title="Change password">
        <form onSubmit={changePassword} className="space-y-3">
          <div>
            <label htmlFor="pw-current" className="mb-1 block text-sm font-medium">Current password</label>
            <input id="pw-current" type="password" className="input" required autoComplete="current-password" value={current} onChange={(e) => setCurrent(e.target.value)} />
          </div>
          <div>
            <label htmlFor="pw-new" className="mb-1 block text-sm font-medium">New password</label>
            <input id="pw-new" type="password" className="input" required minLength={8} autoComplete="new-password" value={next} onChange={(e) => setNext(e.target.value)} />
            <p className="mt-1 text-xs text-slate-500">At least 8 characters with a letter and a number.</p>
          </div>
          <div>
            <label htmlFor="pw-confirm" className="mb-1 block text-sm font-medium">Repeat the new password</label>
            <input id="pw-confirm" type="password" className="input" required autoComplete="new-password" value={confirm} onChange={(e) => setConfirm(e.target.value)} />
          </div>
          <button type="submit" disabled={busy} className="btn-primary">
            {busy && <Loader2 className="h-4 w-4 animate-spin" />} Change password
          </button>
        </form>
      </Card>

      <Card title="System status">
        {!system ? <p className="text-sm text-slate-500">Loading…</p> : (
          <dl className="grid gap-x-6 gap-y-3 text-sm sm:grid-cols-2">
            {rows.map(([k, v]) => (
              <div key={k}><dt className="text-xs text-slate-500">{k}</dt><dd className="break-words font-medium">{v}</dd></div>
            ))}
          </dl>
        )}
      </Card>

      <Card title="Machine-learning components">
        <ul className="space-y-3 text-sm">
          <li>
            <p className="font-medium">Instruction classifier (free text → intervention)</p>
            {nlp?.available ? (
              <p className="text-slate-600">
                Trained on {nlp.n_train} examples ({nlp.embedder}). Cross-validation accuracy {pct(nlp.cv_accuracy)}, held-out accuracy {pct(nlp.held_out_accuracy)}.
                <span className="block text-xs text-slate-500">{nlp.dataset}</span>
              </p>
            ) : <p className="text-slate-500">Not trained yet. It trains itself on first use, or run <code>python -m app.nlp.train</code>.</p>}
          </li>
          <li>
            <p className="font-medium">Intervention-risk predictor</p>
            {ml?.available ? (
              <p className="text-slate-600">
                Selected model: {ml.selected_model?.replace(/_/g, " ")} · data: <strong>{ml.data_source}</strong> ({ml.n_rows} rows).
                {ml.warning && <span className="mt-1 block rounded bg-amber-50 px-2 py-1 text-xs text-amber-900">{ml.warning}</span>}
              </p>
            ) : <p className="text-slate-500">Not trained yet. Run <code>python -m app.ml.train</code>.</p>}
          </li>
        </ul>
      </Card>
    </div>
  );
}
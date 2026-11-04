import { CheckCircle2, Circle, Loader2 } from "lucide-react";
import type { AgentState, AgentStatus } from "../types";

function EngineBadge({ engine }: { engine: string | null }) {
  if (!engine) return null;
  if (engine === "demo")
    return (
      <span className="rounded-full bg-amber-100 px-2.5 py-0.5 text-xs font-semibold text-amber-800">
        Demo mode · simulated tools
      </span>
    );
  return (
    <span className="rounded-full bg-emerald-100 px-2.5 py-0.5 text-xs font-semibold text-emerald-800">
      {engine}
    </span>
  );
}

export default function AgentPanel({ agent, status }: { agent: AgentState; status: AgentStatus }) {
  const running = status === "RUNNING" || status === "PLANNING";
  const failed = status === "FAILED";

  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="font-semibold">Agent</h2>
        <EngineBadge engine={agent.engine} />
      </div>

      <div className="mt-4">
        <div className="mb-1 flex justify-between text-xs text-slate-500">
          <span>Progress</span>
          <span>{agent.progress}%</span>
        </div>
        <div
          className="h-2.5 overflow-hidden rounded-full bg-slate-100"
          role="progressbar"
          aria-valuenow={agent.progress}
          aria-valuemin={0}
          aria-valuemax={100}
        >
          <div
            className={`h-full rounded-full transition-all duration-500 ${failed ? "bg-red-500" : "bg-brand-600"}`}
            style={{ width: `${agent.progress}%` }}
          />
        </div>
      </div>

      <dl className="mt-4 grid gap-3 text-sm sm:grid-cols-2">
        <div>
          <dt className="text-xs text-slate-500">Current step</dt>
          <dd className="font-medium">{agent.current_step ?? "Not started"}</dd>
        </div>
        <div>
          <dt className="text-xs text-slate-500">Agent confidence</dt>
          <dd className="font-medium">
            {agent.confidence !== null ? `${Math.round(agent.confidence * 100)}%` : "–"}
            {agent.engine === "demo" && agent.confidence !== null && (
              <span className="ml-1 text-xs font-normal text-amber-700">(simulated)</span>
            )}
          </dd>
        </div>
      </dl>

      {agent.plan.length > 0 && (
        <ol className="mt-4 space-y-2">
          {agent.plan.map((step, i) => {
            const done = i < agent.step_index;
            const current = i === agent.step_index && running;
            return (
              <li key={i} className="flex items-start gap-2 text-sm">
                {done ? (
                  <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-emerald-600" aria-label="Done" />
                ) : current ? (
                  <Loader2 className="mt-0.5 h-4 w-4 shrink-0 animate-spin text-brand-600" aria-label="In progress" />
                ) : (
                  <Circle className="mt-0.5 h-4 w-4 shrink-0 text-slate-300" aria-label="Pending" />
                )}
                <span className={done ? "text-slate-500" : current ? "font-medium" : "text-slate-700"}>{step}</span>
              </li>
            );
          })}
        </ol>
      )}
    </div>
  );
}
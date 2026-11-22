import type { MemoryItem } from "../types";

const KIND_LABELS: Record<MemoryItem["kind"], string> = {
  FACT: "Fact",
  CORRECTION: "Correction",
  DECISION: "Decision",
  REJECTED_SOURCE: "Rejected source",
  APPROVED_SOURCE: "Approved source",
};

export default function MemoryPanel({ items }: { items: MemoryItem[] }) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <h2 className="mb-1 font-semibold">Session memory</h2>
      <p className="mb-3 text-xs text-slate-500">
        The agent only receives the few items relevant to each step, not everything listed here.
      </p>
      {items.length === 0 ? (
        <p className="text-sm text-slate-500">Nothing remembered yet.</p>
      ) : (
        <ul className="max-h-72 space-y-2 overflow-y-auto pr-1">
          {items.map((m) => (
            <li key={m.id} className="rounded-lg bg-slate-50 px-3 py-2 text-sm">
              <p className="text-xs font-semibold uppercase text-slate-500">
                {KIND_LABELS[m.kind]}
                {m.author && <span className="ml-2 font-normal normal-case">by @{m.author}</span>}
              </p>
              <p className="mt-0.5 break-words text-slate-800">{m.content}</p>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
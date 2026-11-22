import { ClipboardCheck } from "lucide-react";
import type { PendingApproval } from "../types";

interface Props {
  approval: PendingApproval;
  canDecide: boolean;
  canModify: boolean;
  busy: boolean;
  onApprove: () => void;
  onReject: () => void;
  onModify: () => void;
}

export default function ApprovalCard({ approval, canDecide, canModify, busy, onApprove, onReject, onModify }: Props) {
  const isFinal = approval.kind === "FINAL_REPORT";
  return (
    <div role="status" className="rounded-2xl border-2 border-amber-300 bg-amber-50 p-5 shadow-sm">
      <h2 className="flex items-center gap-2 font-semibold text-amber-900">
        <ClipboardCheck className="h-5 w-5" /> Agent is waiting for human approval
      </h2>
      <p className="mt-1 text-sm text-amber-900/80">
        {isFinal
          ? `Review the draft below${approval.payload.round > 1 ? ` (revision ${approval.payload.round})` : ""}. Approve it to finish, or reject it with feedback.`
          : `A review was requested by @${approval.payload.requested_by ?? "someone"}${approval.payload.note ? `: ${approval.payload.note}` : ""}.`}
      </p>
      {isFinal && approval.payload.draft && (
        <pre className="mt-3 max-h-64 overflow-y-auto whitespace-pre-wrap break-words rounded-lg bg-white p-3 text-sm text-slate-800">
          {String(approval.payload.draft)}
        </pre>
      )}
      {canDecide ? (
        <div className="mt-4 flex flex-wrap gap-2">
          <button className="btn-primary" disabled={busy} onClick={onApprove}>Approve</button>
          <button className="btn-secondary" disabled={busy} onClick={onReject}>Reject</button>
          {canModify && (
            <button className="btn-secondary" disabled={busy} onClick={onModify}>Modify task</button>
          )}
        </div>
      ) : (
        <p className="mt-3 text-sm text-amber-900/70">Only the owner or an editor can decide.</p>
      )}
    </div>
  );
}
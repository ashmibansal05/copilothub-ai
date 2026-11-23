import type { ConstraintAction, InterventionType, Priority } from "../types";

export const INTERVENTION_LABELS: Record<InterventionType, string> = {
  APPROVE: "Approved",
  REJECT: "Rejected",
  CORRECT: "Correction",
  PAUSE: "Paused",
  RESUME: "Resumed",
  MODIFY_TASK: "Changed the task",
  ADD_INFORMATION: "Added information",
  ADD_CONSTRAINT: "Added a constraint",
  REMOVE_CONSTRAINT: "Removed a constraint",
  REJECT_SOURCE: "Rejected a source",
  CHANGE_SOURCE: "Changed a source",
  REQUEST_REVIEW: "Requested a review",
  COMMENT: "Comment",
  RESOLVE_CONFLICT: "Resolved a conflict",
};

export const ACTION_LABELS: Record<ConstraintAction, string> = {
  EXCLUDE_SOURCE: "Exclude source",
  INCLUDE_SOURCE: "Allow source",
  PREFER_SOURCE: "Prefer source",
  INSTRUCTION: "Instruction",
};

export const PRIORITY_STYLES: Record<Priority, string> = {
  HIGH: "bg-red-100 text-red-700",
  MEDIUM: "bg-amber-100 text-amber-800",
  LOW: "bg-slate-100 text-slate-600",
};
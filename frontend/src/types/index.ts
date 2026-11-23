export type UserRole = "OWNER" | "EDITOR" | "VIEWER";

export interface User {
  id: string;
  email: string;
  username: string;
  full_name: string;
  role: UserRole;
  is_active: boolean;
  created_at: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
}

export interface RegisterPayload {
  email: string;
  username: string;
  full_name: string;
  password: string;
}

export interface HealthResponse {
  status: string;
  app: string;
  environment: string;
  demo_mode: boolean;
}

// ---------- Sessions (Phase 3) ----------

export type AgentStatus =
  | "CREATED"
  | "PLANNING"
  | "RUNNING"
  | "WAITING_FOR_APPROVAL"
  | "PAUSED"
  | "COMPLETED"
  | "FAILED"
  | "CANCELLED";

export interface Member {
  user_id: string;
  username: string;
  full_name: string;
  role: UserRole;
  joined_at: string;
}

export interface SessionSummary {
  id: string;
  name: string;
  task: string;
  status: AgentStatus;
  my_role: UserRole;
  member_count: number;
  owner_username: string;
  created_at: string;
}

export interface SessionDetail extends SessionSummary {
  owner_id: string;
  members: Member[];
  editor_code: string | null;
  viewer_code: string | null;
  started_at: string | null;
  ended_at: string | null;
}

export interface InvitePreview {
  session_name: string;
  task: string;
  owner_name: string;
  role: UserRole;
  already_member: boolean;
  session_id: string | null;
}

export type ControlAction = "start" | "pause" | "resume" | "stop";

// ---------- Real-time events (Phase 4) ----------

export interface SessionEvent {
  id: string;
  session_id: string;
  type: string;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  payload: Record<string, any>;
  user_id: string | null;
  created_at: string;
}

export interface OnlineUser {
  user_id: string;
  username: string;
  role: UserRole;
}
// ---------- Agent (Phase 5) ----------

// ---------- Interventions, constraints, memory (Phases 7-8) ----------

export type InterventionType =
  | "APPROVE" | "REJECT" | "CORRECT" | "PAUSE" | "RESUME" | "MODIFY_TASK"
  | "ADD_INFORMATION" | "ADD_CONSTRAINT" | "REMOVE_CONSTRAINT" | "REJECT_SOURCE"
  | "CHANGE_SOURCE" | "REQUEST_REVIEW" | "COMMENT" | "RESOLVE_CONFLICT";

export type Priority = "LOW" | "MEDIUM" | "HIGH";
export type ConstraintAction = "EXCLUDE_SOURCE" | "INCLUDE_SOURCE" | "PREFER_SOURCE" | "INSTRUCTION";

export interface Intervention {
  id: string;
  session_id: string;
  user_id: string | null;
  username: string | null;
  type: InterventionType;
  content: string | null;
  target: string | null;
  priority: Priority;
  status: string;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  details: Record<string, any>;
  result: string | null;
  created_at: string;
}

export interface Constraint {
  id: string;
  session_id: string;
  type: "CONSTRAINT";
  action: ConstraintAction;
  target: string;
  description: string;
  priority: Priority;
  status: string;
  created_by: string | null;
  created_by_username: string | null;
  created_at: string;
}

export interface PendingApproval {
  id: string;
  kind: "FINAL_REPORT" | "REVIEW";
  status: string;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  payload: Record<string, any>;
  created_at: string;
}

export interface MemoryItem {
  id: string;
  kind: "FACT" | "CORRECTION" | "DECISION" | "REJECTED_SOURCE" | "APPROVED_SOURCE";
  key: string | null;
  content: string;
  importance: number;
  author: string | null;
  created_at: string;
}

export interface MemoryView {
  constraints: Constraint[];
  items: MemoryItem[];
}

export interface InterventionPayload {
  type: InterventionType;
  content?: string;
  target?: string;
  priority?: Priority;
  action?: ConstraintAction;
  constraint_id?: string;
  origin_text?: string;
}

export interface AgentState {
  session_id: string;
  status: AgentStatus;
  current_task: string;
  current_step: string | null;
  step_index: number; // steps completed so far
  total_steps: number;
  progress: number;
  confidence: number | null;
  engine: string | null;
  plan: string[];
  recent_actions: Record<string, unknown>[];
  tool_results: Record<string, unknown>[];
  active_constraints: Constraint[];
  human_interventions: Intervention[]; // most recent first
  pending_approval: PendingApproval | null;
    open_conflicts: Conflict[];
}
// ---------- Conflicts (Phase 9) ----------

export interface ConflictSide {
  constraint_id: string;
  action: ConstraintAction;
  target: string;
  description: string;
  priority: Priority;
  created_by_username: string | null;
  created_by_role: string | null;
  still_active: boolean;
}

export interface Conflict {
  id: string;
  session_id: string;
  kind: "SOURCE_POLICY";
  status: "OPEN" | "RESOLVED";
  constraint_a: ConflictSide; // the older instruction
  constraint_b: ConflictSide; // the newer instruction
  requires_resolution: boolean;
  rule_applied: string;
  provisional: string | null;
  suggested_winner_id: string | null;
  resolution: "KEEP_A" | "KEEP_B" | "REMOVE_BOTH" | "AUTO_CLOSED" | null;
  resolution_note: string | null;
  resolved_by_username: string | null;
  created_at: string;
  resolved_at: string | null;
}

// ---------- Documents / RAG (Phase 10) ----------

export interface DocumentInfo {
  id: string;
  session_id: string;
  title: string;
  filename: string;
  source_name: string;
  source_type: string;
  status: "PROCESSING" | "READY" | "FAILED";
  error: string | null;
  size_bytes: number;
  page_count: number | null;
  chunk_count: number;
  flagged_chunks: number;
  embedding_backend: string | null;
  uploaded_by_username: string | null;
  created_at: string;
}

export interface ChunkInfo {
  id: string;
  chunk_index: number;
  page: number | null;
  text: string;
  flagged: boolean;
}

export interface SearchHit {
  chunk_id: string;
  document_id: string;
  title: string;
  source_name: string;
  source_type: string;
  page: number | null;
  text: string;
  score: number;
  preferred: boolean;
}
// ---------- Reports (Phase 11) ----------

export interface ReportSection {
  key: string;
  title: string;
  body: string;
}

export interface ReportSummary {
  id: string;
  title: string;
  format: string;
  origin: string;
  status: string;
  kind: "DRAFT" | "FINAL";
  engine: string | null;
  chars: number;
  created_at: string;
}

export interface ReportDetail extends ReportSummary {
  content: string;
  sections: ReportSection[] | null;
}

// ---------- ML risk (Phase 13) ----------

export interface RiskFactor {
  feature: string;
  label: string;
  effect: number;
  value: number;
}

export interface RiskEstimate {
  available: boolean;
  reason?: string | null;
  probability?: number | null;
  level?: "LOW" | "MEDIUM" | "HIGH" | null;
  model?: string | null;
  data_source?: string | null;
  step_index?: number | null;
  factors: RiskFactor[];
  warning?: string | null;
}

export interface ModelScores {
  cv_roc_auc_mean: number;
  cv_roc_auc_std: number;
  test: { accuracy: number; precision: number; recall: number; f1: number; roc_auc: number };
}

export interface MLStatus {
  available: boolean;
  data_source?: string | null;
  trained_at?: string | null;
  selected_model?: string | null;
  selection_rule?: string | null;
  n_rows?: number | null;
  n_test?: number | null;
  positive_rate?: number | null;
  models: Record<string, ModelScores>;
  baseline?: { accuracy: number; precision: number; recall: number; f1: number; roc_auc: number; rule: string } | null;
  warning?: string | null;
}

// ---------- Analytics (Phase 14) ----------

export interface ToolStat { tool: string; calls: number; failures: number }
export interface RiskSummary {
  data_source: string | null;
  n: number;
  mean: number | null;
  max: number | null;
  last: number | null;
  history: { step_index: number; probability: number; level: string }[];
  observed_n: number;
  mean_when_intervened: number | null;
  mean_when_not: number | null;
}

export interface SessionAnalytics {
  session_id: string;
  name: string;
  status: string;
  engine: string | null;
  duration_seconds: number | null;
  steps_planned: number;
  steps_completed: number;
  confidence_series: { step_index: number; confidence: number }[];
  avg_confidence: number | null;
  final_confidence: number | null;
  min_confidence: number | null;
  interventions_total: number;
  comments: number;
  corrective: number;
  interventions_by_type: Record<string, number>;
  interventions_by_user: Record<string, number>;
  tool_calls: number;
  tool_failures: number;
  tool_failure_rate: number | null;
  tools: ToolStat[];
  failed_attempts: number;
  recovered: boolean;
  approvals_requested: number;
  approvals_approved: number;
  approvals_rejected: number;
  approval_rate: number | null;
  conflicts_total: number;
  conflicts_open: number;
  conflicts_resolved: number;
  sources_used: number;
  sources_rejected: number;
  source_rejection_rate: number | null;
  documents: number;
  risk: RiskSummary;
}

export interface ResearchGroup {
  label: string;
  sessions: number;
  completion_rate: number | null;
  avg_duration_seconds: number | null;
  avg_final_confidence: number | null;
}

export interface AnalyticsOverview {
  sessions_total: number;
  sessions_completed: number;
  sessions_failed: number;
  sessions_cancelled: number;
  sessions_active: number;
  success_rate: number | null;
  avg_duration_seconds: number | null;
  interventions_total: number;
  interventions_corrective: number;
  interventions_per_session: number | null;
  interventions_by_type: Record<string, number>;
  avg_confidence: number | null;
  avg_final_confidence: number | null;
  confidence_histogram: { label: string; count: number }[];
  tool_calls: number;
  tool_failures: number;
  tool_failure_rate: number | null;
  tools: ToolStat[];
  approvals_requested: number;
  approvals_approved: number;
  approvals_rejected: number;
  approval_rate: number | null;
  conflicts_total: number;
  conflicts_open: number;
  sources_used: number;
  sources_rejected: number;
  source_rejection_rate: number | null;
  prediction: RiskSummary;
  research: {
    task_completion_rate: number | null;
    human_correction_rate: number | null;
    incorrect_actions_per_session: number | null;
    agent_recovery_rate: number | null;
    avg_time_to_completion_seconds: number | null;
    source_rejection_rate: number | null;
    tool_failure_rate: number | null;
    conflicts_per_session: number | null;
    groups: ResearchGroup[];
    notes: string;
  };
  recent_sessions: {
    id: string;
    name: string;
    status: string;
    created_at: string;
    duration_seconds: number | null;
    interventions: number;
    corrective: number;
    tool_failures: number;
    conflicts: number;
    final_confidence: number | null;
  }[];
}

// ---------- Free-text instructions (Phase 12) ----------

export interface InstructionProposal {
  type: InterventionType;
  content: string | null;
  target: string | null;
  action: ConstraintAction | null;
  priority: Priority | null;
  constraint_id: string | null;
  candidates: { id: string; description: string }[];
}

export interface InstructionResult {
  text: string;
  intent: string;
  confidence: number;
  method: "model" | "rule";
  alternatives: { intent: string; confidence: number }[];
  proposal: InstructionProposal;
  allowed: boolean;
  needs_confirmation: boolean;
  reason: string | null;
  note: string | null;
  applied: boolean;
  intervention: Intervention | null;
}
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
  | "CHANGE_SOURCE" | "REQUEST_REVIEW" | "COMMENT";

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
}
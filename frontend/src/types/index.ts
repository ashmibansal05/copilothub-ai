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
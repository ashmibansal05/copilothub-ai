import type { AgentState, AgentStatus, SessionEvent } from "../types";

export function emptyAgentState(sessionId: string, task: string, status: AgentStatus): AgentState {
  return {
    session_id: sessionId,
    status,
    current_task: task,
    current_step: null,
    step_index: 0,
    total_steps: 0,
    progress: 0,
    confidence: null,
    engine: null,
    plan: [],
    recent_actions: [],
    tool_results: [],
    active_constraints: [],
    human_interventions: [],
    pending_approval: null,
  };
}

/** Folds one live event into the agent snapshot loaded from GET /state. */
export function applyAgentEvent(prev: AgentState, e: SessionEvent): AgentState {
  const p = e.payload;
  switch (e.type) {
    case "STEP_STARTED":
      return {
        ...prev,
        current_step: p.step ?? prev.current_step,
        total_steps: p.total_steps || prev.total_steps,
        progress: p.progress ?? prev.progress,
        engine: p.engine ?? prev.engine,
      };
    case "STEP_COMPLETED":
      return {
        ...prev,
        plan: p.plan ?? prev.plan,
        total_steps: p.total_steps || prev.total_steps,
        step_index: p.completed_steps ?? prev.step_index,
        progress: p.progress ?? prev.progress,
        confidence: p.confidence ?? prev.confidence,
      };
    case "COMPLETED":
      return { ...prev, current_step: "Completed", progress: 100, step_index: prev.total_steps };
    case "FAILED":
      return { ...prev, current_step: "Failed" };
    default:
      return prev;
  }
}
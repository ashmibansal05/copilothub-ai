
import type {
  AgentState,
  AgentStatus,
  Conflict,
  Constraint,
  Intervention,
  SessionEvent,
} from "../types";

export function emptyAgentState(
  sessionId: string,
  task: string,
  status: AgentStatus
): AgentState {
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

    // Phase 9: Conflict resolution
    open_conflicts: [],
  };
}

/** Folds one live event into the agent snapshot loaded from GET /state. */
export function applyAgentEvent(
  prev: AgentState,
  e: SessionEvent
): AgentState {
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
      return {
        ...prev,
        current_step: "Completed",
        progress: 100,
        step_index: prev.total_steps,
        pending_approval: null,
      };

    case "FAILED":
      return {
        ...prev,
        current_step: "Failed",
        pending_approval: null,
      };

    // ============================================================
    // Phase 8: Constraints
    // ============================================================

    case "CONSTRAINT_ADDED": {
      const c = p.constraint as Constraint;

      return prev.active_constraints.some((x) => x.id === c.id)
        ? prev
        : {
            ...prev,
            active_constraints: [...prev.active_constraints, c],
          };
    }

    case "CONSTRAINT_REMOVED":
      return {
        ...prev,
        active_constraints: prev.active_constraints.filter(
          (c) => c.id !== p.constraint_id
        ),
      };

    // ============================================================
    // Phase 9: Conflict Resolution
    // ============================================================

    case "CONFLICT_DETECTED": {
      const c = p.conflict as Conflict;

      return prev.open_conflicts.some((x) => x.id === c.id)
        ? prev
        : {
            ...prev,
            open_conflicts: [...prev.open_conflicts, c],
          };
    }

    case "CONFLICT_RESOLVED": {
      const c = p.conflict as Conflict;

      return {
        ...prev,
        open_conflicts: prev.open_conflicts.filter(
          (x) => x.id !== c.id
        ),
      };
    }

    // ============================================================
    // Phase 7: Human Approvals and Interventions
    // ============================================================

    case "APPROVAL_REQUESTED":
      return {
        ...prev,
        pending_approval: {
          id: p.approval_id,
          kind: p.kind,
          status: "PENDING",
          payload: p.payload ?? {},
          created_at: e.created_at,
        },
      };

    case "APPROVAL_COMPLETED":
      return {
        ...prev,
        pending_approval: null,
      };

    case "HUMAN_INTERVENTION": {
      const iv = p.intervention as Intervention;

      if (prev.human_interventions.some((x) => x.id === iv.id)) {
        return prev;
      }

      return {
        ...prev,
        human_interventions: [
          iv,
          ...prev.human_interventions,
        ].slice(0, 20),
        current_task:
          iv.type === "MODIFY_TASK" && iv.content
            ? iv.content
            : prev.current_task,
      };
    }

    default:
      return prev;
  }
}
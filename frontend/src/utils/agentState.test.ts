import { describe, expect, it } from "vitest";
import type { Constraint, Conflict, Intervention, SessionEvent } from "../types";
import { applyAgentEvent, emptyAgentState } from "./agentState";

let n = 0;
const event = (type: string, payload: Record<string, unknown> = {}): SessionEvent => ({
  id: `e${n++}`, session_id: "s", type, payload, user_id: null, created_at: "2026-01-01T00:00:00Z",
});
const base = emptyAgentState("s", "the task", "RUNNING");

const constraint = (id: string): Constraint => ({
  id, session_id: "s", type: "CONSTRAINT", action: "EXCLUDE_SOURCE", target: "Wikipedia",
  description: "Do not use Wikipedia", priority: "HIGH", status: "ACTIVE", created_by: null,
  created_by_username: "bob", created_at: "2026-01-01T00:00:00Z",
});

const intervention = (id: string, type: Intervention["type"], content: string | null = null): Intervention => ({
  id, session_id: "s", user_id: null, username: "bob", type, content, target: null, priority: "MEDIUM",
  status: "APPLIED", details: {}, result: null, created_at: "2026-01-01T00:00:00Z",
});

describe("applyAgentEvent", () => {
  it("tracks the current step and plan progress", () => {
    const started = applyAgentEvent(base, event("STEP_STARTED", { step: "Gather AWS", total_steps: 7, progress: 20, engine: "demo" }));
    expect(started).toMatchObject({ current_step: "Gather AWS", total_steps: 7, progress: 20, engine: "demo" });
    const done = applyAgentEvent(started, event("STEP_COMPLETED", { completed_steps: 3, progress: 45, confidence: 0.8, plan: ["a", "b"] }));
    expect(done).toMatchObject({ step_index: 3, progress: 45, confidence: 0.8, plan: ["a", "b"] });
  });

  it("adds constraints once and removes them by id", () => {
    const added = applyAgentEvent(base, event("CONSTRAINT_ADDED", { constraint: constraint("c1") }));
    expect(applyAgentEvent(added, event("CONSTRAINT_ADDED", { constraint: constraint("c1") })).active_constraints).toHaveLength(1);
    expect(applyAgentEvent(added, event("CONSTRAINT_REMOVED", { constraint_id: "c1" })).active_constraints).toHaveLength(0);
  });

  it("sets and clears the pending approval", () => {
    const asked = applyAgentEvent(base, event("APPROVAL_REQUESTED", { approval_id: "a1", kind: "FINAL_REPORT", payload: { draft: "x" } }));
    expect(asked.pending_approval).toMatchObject({ id: "a1", kind: "FINAL_REPORT", status: "PENDING" });
    expect(applyAgentEvent(asked, event("APPROVAL_COMPLETED", { approved: true })).pending_approval).toBeNull();
  });

  it("tracks open conflicts", () => {
    const conflict = { id: "k1" } as Conflict;
    const detected = applyAgentEvent(base, event("CONFLICT_DETECTED", { conflict }));
    expect(detected.open_conflicts).toHaveLength(1);
    expect(applyAgentEvent(detected, event("CONFLICT_DETECTED", { conflict })).open_conflicts).toHaveLength(1);
    expect(applyAgentEvent(detected, event("CONFLICT_RESOLVED", { conflict })).open_conflicts).toHaveLength(0);
  });

  it("records interventions without duplicates and applies task changes", () => {
    const modify = intervention("i1", "MODIFY_TASK", "A brand new task");
    const once = applyAgentEvent(base, event("HUMAN_INTERVENTION", { intervention: modify }));
    expect(once.current_task).toBe("A brand new task");
    expect(applyAgentEvent(once, event("HUMAN_INTERVENTION", { intervention: modify })).human_interventions).toHaveLength(1);
    let state = base;
    for (let i = 0; i < 25; i++) state = applyAgentEvent(state, event("HUMAN_INTERVENTION", { intervention: intervention(`x${i}`, "COMMENT", "hi") }));
    expect(state.human_interventions).toHaveLength(20);
    expect(state.human_interventions[0].id).toBe("x24"); // newest first
  });

  it("finishes cleanly and ignores unknown events", () => {
    const pending = { ...base, total_steps: 5, pending_approval: { id: "a", kind: "REVIEW" as const, status: "PENDING", payload: {}, created_at: "" } };
    expect(applyAgentEvent(pending, event("COMPLETED"))).toMatchObject({ progress: 100, step_index: 5, pending_approval: null });
    expect(applyAgentEvent(base, event("SOMETHING_ELSE"))).toBe(base);
  });
});
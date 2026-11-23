import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { SessionEvent } from "../types";
import EventTimeline from "./EventTimeline";

let n = 0;
const event = (type: string, payload: Record<string, unknown>): SessionEvent => ({
  id: `e${n++}`, session_id: "s", type, payload, user_id: null, created_at: `2026-01-01T00:00:0${n}Z`,
});

describe("EventTimeline", () => {
  it("shows an empty state", () => {
    render(<EventTimeline events={[]} />);
    expect(screen.getByText("No activity yet.")).toBeInTheDocument();
  });

  it("describes agent, constraint and approval events in plain language", () => {
    render(<EventTimeline events={[
      event("STEP_STARTED", { phase: "ACT", step_index: 2, total_steps: 7, step: "Gather information on AWS" }),
      event("STATUS_CHANGED", { previous_status: "RUNNING", status: "PAUSED" }),
      event("CONSTRAINT_ADDED", { actor: { username: "alice" }, constraint: { description: "Do not use Wikipedia" } }),
      event("APPROVAL_COMPLETED", { actor: { username: "owner" }, approved: true, kind: "FINAL_REPORT" }),
    ]} />);
    expect(screen.getByText("Step 2/7: Gather information on AWS")).toBeInTheDocument();
    expect(screen.getByText("Status: RUNNING → PAUSED")).toBeInTheDocument();
    expect(screen.getByText("alice added a constraint: Do not use Wikipedia")).toBeInTheDocument();
    expect(screen.getByText("owner approved the final draft")).toBeInTheDocument();
  });

  it("lists the newest event first", () => {
    render(<EventTimeline events={[
      event("COMPLETED", {}),
      event("FAILED", { error: "disk full" }),
    ]} />);
    const items = screen.getAllByRole("listitem");
    expect(items[0]).toHaveTextContent("Agent failed: disk full");
    expect(items[1]).toHaveTextContent("Agent completed the task");
  });
});
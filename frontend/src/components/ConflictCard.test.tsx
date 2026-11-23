import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { Conflict, ConflictSide } from "../types";
import ConflictCard from "./ConflictCard";

const side = (id: string, description: string, user: string): ConflictSide => ({
  constraint_id: id, action: "EXCLUDE_SOURCE", target: "Wikipedia", description, priority: "MEDIUM",
  created_by_username: user, created_by_role: "editor", still_active: true,
});

const conflict: Conflict = {
  id: "c1", session_id: "s", kind: "SOURCE_POLICY", status: "OPEN",
  constraint_a: side("a1", 'Sources from "Wikipedia" are explicitly allowed.', "bob"),
  constraint_b: side("b1", 'Do not use sources from or about "Wikipedia".', "dave"),
  requires_resolution: true, rule_applied: "Same priority and same role.", provisional: "Enforced for now: the restrictive option.",
  suggested_winner_id: null, resolution: null, resolution_note: null, resolved_by_username: null,
  created_at: "2026-01-01T00:00:00Z", resolved_at: null,
};

describe("ConflictCard", () => {
  it("shows both instructions side by side with the rule and what is enforced", () => {
    render(<ConflictCard conflicts={[conflict]} isOwner={false} busy={false} onResolve={vi.fn()} />);
    expect(screen.getByText(/explicitly allowed/)).toBeInTheDocument();
    expect(screen.getByText(/Do not use sources from or about/)).toBeInTheDocument();
    expect(screen.getByText(/Same priority and same role/)).toBeInTheDocument();
    expect(screen.getByText(/Enforced for now/)).toBeInTheDocument();
    expect(screen.getByText("agent is waiting for the owner")).toBeInTheDocument();
  });

  it("lets only the owner decide", async () => {
    const user = userEvent.setup();
    const onResolve = vi.fn();
    render(<ConflictCard conflicts={[conflict]} isOwner busy={false} onResolve={onResolve} />);
    await user.click(screen.getByRole("button", { name: "Keep A" }));
    await user.click(screen.getByRole("button", { name: "Keep B" }));
    await user.click(screen.getByRole("button", { name: "Remove both" }));
    expect(onResolve.mock.calls).toEqual([["c1", "a1"], ["c1", "b1"], ["c1", null]]);
  });

  it("gives non-owners no buttons", () => {
    render(<ConflictCard conflicts={[conflict]} isOwner={false} busy={false} onResolve={vi.fn()} />);
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    expect(screen.getByText("Only the session owner can resolve this conflict.")).toBeInTheDocument();
  });

  it("renders nothing without conflicts", () => {
    const { container } = render(<ConflictCard conflicts={[]} isOwner busy={false} onResolve={vi.fn()} />);
    expect(container).toBeEmptyDOMElement();
  });
});
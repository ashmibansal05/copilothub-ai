import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { InstructionResult } from "../types";
import InstructionBox from "./InstructionBox";

const result = (over: Partial<InstructionResult> = {}): InstructionResult => ({
  text: "Do not use Wikipedia.", intent: "REJECT_SOURCE", confidence: 0.95, method: "model", alternatives: [],
  proposal: { type: "REJECT_SOURCE", content: null, target: "Wikipedia", action: null, priority: null, constraint_id: null, candidates: [] },
  allowed: true, needs_confirmation: false, reason: null, note: null, applied: true, intervention: null, ...over,
});

const box = (onSubmit: () => Promise<InstructionResult>, onNeeds = vi.fn()) => {
  render(<InstructionBox onSubmit={onSubmit} onNeedsConfirmation={onNeeds} />);
  return { input: screen.getByLabelText("Instruction for the agent"), onNeeds };
};

describe("InstructionBox", () => {
  it("reports an applied instruction and clears the field", async () => {
    const user = userEvent.setup();
    const { input } = box(vi.fn().mockResolvedValue(result()));
    await user.type(input, "Do not use Wikipedia.{enter}");
    expect(await screen.findByText(/Applied \(95% sure/)).toBeInTheDocument();
    expect(input).toHaveValue("");
  });

  it("hands uncertain instructions to the confirmation dialog", async () => {
    const user = userEvent.setup();
    const uncertain = result({ applied: false, needs_confirmation: true, confidence: 0.5, reason: "I am only 50% sure" });
    const { input, onNeeds } = box(vi.fn().mockResolvedValue(uncertain));
    await user.type(input, "maybe skip that site{enter}");
    await vi.waitFor(() => expect(onNeeds).toHaveBeenCalledWith(uncertain));
    expect(input).toHaveValue("maybe skip that site"); // kept so the user can retry
  });

  it("explains when the role may not do that", async () => {
    const user = userEvent.setup();
    const { input } = box(vi.fn().mockResolvedValue(result({ applied: false, allowed: false, reason: "Your role (editor) may not perform MODIFY_TASK." })));
    await user.type(input, "change the task{enter}");
    expect(await screen.findByText(/may not perform MODIFY_TASK/)).toBeInTheDocument();
  });

  it("shows server errors", async () => {
    const user = userEvent.setup();
    const { input } = box(vi.fn().mockRejectedValue(new Error("x")));
    await user.type(input, "hello there{enter}");
    expect(await screen.findByText("Something went wrong")).toBeInTheDocument();
  });
});
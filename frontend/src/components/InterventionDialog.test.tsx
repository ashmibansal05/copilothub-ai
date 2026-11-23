import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import InterventionDialog from "./InterventionDialog";

describe("InterventionDialog", () => {
  it("submits a structured exclusion constraint", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    const onClose = vi.fn();
    render(<InterventionDialog kind="CONSTRAINT" onClose={onClose} onSubmit={onSubmit} />);

    await user.type(screen.getByLabelText(/source name, website or type/i), "Wikipedia");
    await user.click(screen.getByRole("button", { name: "Add constraint" }));

    expect(onSubmit).toHaveBeenCalledWith({ type: "ADD_CONSTRAINT", action: "EXCLUDE_SOURCE", target: "Wikipedia", priority: "MEDIUM" });
    await waitFor(() => expect(onClose).toHaveBeenCalled());
  });

  it("sends a comment as plain content", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    render(<InterventionDialog kind="COMMENT" onClose={vi.fn()} onSubmit={onSubmit} />);
    await user.type(screen.getByLabelText("Comment"), "hello world");
    await user.click(screen.getByRole("button", { name: "Post comment" }));
    expect(onSubmit).toHaveBeenCalledWith({ type: "COMMENT", content: "hello world" });
  });

  it("shows the error and stays open when the server refuses", async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    render(<InterventionDialog kind="COMMENT" onClose={onClose} onSubmit={vi.fn().mockRejectedValue(new Error("boom"))} />);
    await user.type(screen.getByLabelText("Comment"), "hello world");
    await user.click(screen.getByRole("button", { name: "Post comment" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Something went wrong");
    expect(onClose).not.toHaveBeenCalled();
  });

  it("closes with the Escape key", async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    render(<InterventionDialog kind="COMMENT" onClose={onClose} onSubmit={vi.fn()} />);
    await user.keyboard("{Escape}");
    expect(onClose).toHaveBeenCalled();
  });
});
import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import SourceCodePanel from "./SourceCodePanel";

vi.mock("../services/codeService", () => ({ codeService: {
  list: vi.fn(async () => ({ task_type: "CODING", generating: false, files: [
    { id: "a", path: "main.py", language: "python", version: 1, validation_status: "SYNTAX_VALIDATED" }
  ] })),
  review: vi.fn(async () => ({ status: "PENDING", approval_id: "r1", versions: { "main.py": 1 }, note: null })),
  decideReview: vi.fn(async () => ({ status: "APPROVED", approval_id: "r1", versions: { "main.py": 1 }, note: null })),
  file: vi.fn(async () => ({ id: "a", path: "main.py", language: "python", version: 1,
      validation_status: "SYNTAX_VALIDATED", validation_details: "Python AST syntax validation passed",
      content: "print(42)\n" })),
  versions: vi.fn(async () => ([{ version: 1, origin: "AI", validation_status: "SYNTAX_VALIDATED", created_at: "2026-01-01" }])),
} }));

describe("SourceCodePanel", () => {
  it("shows generated project file and source contents", async () => {
    render(<SourceCodePanel sessionId="s" canEdit={false} />);
    await waitFor(() => expect(screen.getByText("print(42)")).toBeInTheDocument());
    expect(screen.getByText(/Files saved for everyone on your team/)).toBeInTheDocument();
    expect(screen.getByTitle("main.py")).toBeInTheDocument();
  });
  it("shows the owner-only review gate", async () => {
    render(<SourceCodePanel sessionId="s" canEdit canApprove />);
    await waitFor(() => expect(screen.getByText("Approve code and finalize report")).toBeInTheDocument());
    expect(screen.getByText("Request changes")).toBeDisabled();
  });
});

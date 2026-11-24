import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import ReportBody from "./ReportBody";

describe("ReportBody", () => {
  it("renders report subsections, bullet points and readable fenced code", () => {
    render(<ReportBody body={"### main.py (v1)\n\n```python\nprint(42)\n```\n\n- Syntax validated\n- Runtime not tested"} />);
    expect(screen.getByRole("heading", { name: "main.py (v1)" })).toBeInTheDocument();
    expect(screen.getByText("print(42)")).toBeInTheDocument();
    expect(screen.getByText("Runtime not tested")).toBeInTheDocument();
  });

  it("renders any HTML-like text safely as ordinary text", () => {
    const { container } = render(<ReportBody body={"<script>alert('x')</script>"} />);
    expect(container.querySelector("script")).toBeNull();
    expect(screen.getByText(/<script>/)).toBeInTheDocument();
  });
});

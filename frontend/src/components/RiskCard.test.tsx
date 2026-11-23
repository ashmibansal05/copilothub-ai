import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { RiskEstimate } from "../types";
import RiskCard from "./RiskCard";

const estimate: RiskEstimate = {
  available: true, probability: 0.72, level: "HIGH", model: "random_forest", data_source: "synthetic", step_index: 3,
  factors: [{ feature: "agent_confidence", label: "Agent confidence on this step", effect: 0.12, value: 0.3 }],
  warning: "SYNTHETIC DATA",
};

describe("RiskCard", () => {
  it("explains that nothing is available before the first step", () => {
    render(<RiskCard risk={null} history={[]} />);
    expect(screen.getByText("Appears after the first completed step.")).toBeInTheDocument();
  });

  it("shows the reason when the model is unavailable", () => {
    render(<RiskCard risk={{ available: false, reason: "The risk model is unavailable", factors: [] }} history={[]} />);
    expect(screen.getByText("The risk model is unavailable")).toBeInTheDocument();
  });

  it("shows the probability, level, drivers and a synthetic-data notice", () => {
    render(<RiskCard risk={estimate} history={[0.2, 0.5, 0.72]} />);
    expect(screen.getByText("72%")).toBeInTheDocument();
    expect(screen.getByText("HIGH")).toBeInTheDocument();
    expect(screen.getByText("Agent confidence on this step")).toBeInTheDocument();
    expect(screen.getByText("+12 pts")).toBeInTheDocument();
    expect(screen.getByText(/SYNTHETIC/)).toBeInTheDocument();
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "72");
  });

  it("does not call real-data estimates synthetic", () => {
    render(<RiskCard risk={{ ...estimate, data_source: "real", warning: null }} history={[]} />);
    expect(screen.queryByText(/SYNTHETIC/)).not.toBeInTheDocument();
  });
});
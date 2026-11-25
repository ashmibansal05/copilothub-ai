
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { RiskEstimate } from "../types";
import RiskCard from "./RiskCard";

const estimate: RiskEstimate = {
  available: true,
  probability: 0.72,
  level: "HIGH",
  step_index: 3,
  factors: [
  {
    feature: "agent_confidence",
    label: "Agent confidence on this step",
    effect: 0.12,
    value: 0.3,
  },
],
};

describe("RiskCard", () => {
  it("explains that nothing is available before the first step", () => {
    render(<RiskCard risk={null} history={[]} />);

    expect(
      screen.getByText("Appears after the first completed step.")
    ).toBeInTheDocument();
  });

  it("shows the reason when the model is unavailable", () => {
    const unavailableRisk: RiskEstimate = {
      available: false,
      probability: null,
      level: null,
      reason: "The risk model is unavailable",
      step_index: 0,
      factors: [],
    };

    render(<RiskCard risk={unavailableRisk} history={[]} />);

    expect(
      screen.getByText("The risk model is unavailable")
    ).toBeInTheDocument();
  });

  it("shows the probability, level, and risk factors", () => {
    render(
      <RiskCard
        risk={estimate}
        history={[0.2, 0.5, 0.72]}
      />
    );

    expect(screen.getByText("72%")).toBeInTheDocument();
    expect(screen.getByText("HIGH")).toBeInTheDocument();

    expect(
      screen.getByText("Agent confidence on this step")
    ).toBeInTheDocument();

    expect(screen.getByText("+12 pts")).toBeInTheDocument();

    expect(screen.getByRole("progressbar")).toHaveAttribute(
      "aria-valuenow",
      "72"
    );
  });

  it("shows the risk history correctly", () => {
    render(
      <RiskCard
        risk={estimate}
        history={[0.2, 0.5, 0.72]}
      />
    );

    expect(screen.getByLabelText("Risk after each step")).toBeInTheDocument();
    expect(screen.getByTitle("20%")).toBeInTheDocument();
    expect(screen.getByTitle("50%")).toBeInTheDocument();
    expect(screen.getByTitle("72%")).toBeInTheDocument();
  });
});

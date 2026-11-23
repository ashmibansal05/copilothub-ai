import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ToastProvider, useToast } from "./ToastContext";

function Demo() {
  const toast = useToast();
  return (
    <>
      <button onClick={() => toast.success("Saved!")}>ok</button>
      <button onClick={() => toast.error("It failed")}>fail</button>
    </>
  );
}

describe("ToastProvider", () => {
    beforeEach(() => {
    vi.useFakeTimers();
    });

    afterEach(() => {
    vi.useRealTimers();
    });

  it("shows a message and removes it after a few seconds", () => {
    render(<ToastProvider><Demo /></ToastProvider>);
    fireEvent.click(screen.getByText("ok"));
    expect(screen.getByText("Saved!")).toBeInTheDocument();
    act(() => { vi.advanceTimersByTime(6000); });
    expect(screen.queryByText("Saved!")).not.toBeInTheDocument();
  });

  it("announces errors as alerts, keeps them longer, and lets users dismiss them", () => {
    render(<ToastProvider><Demo /></ToastProvider>);
    fireEvent.click(screen.getByText("fail"));
    expect(screen.getByRole("alert")).toHaveTextContent("It failed");
    act(() => { vi.advanceTimersByTime(6000); });
    expect(screen.getByText("It failed")).toBeInTheDocument();
    fireEvent.click(screen.getByLabelText("Dismiss notification"));
    expect(screen.queryByText("It failed")).not.toBeInTheDocument();
  });

  it("refuses to be used outside its provider", () => {
    const spy = vi.spyOn(console, "error").mockImplementation(() => undefined);
    expect(() => render(<Demo />)).toThrow(/ToastProvider/);
    spy.mockRestore();
  });
});
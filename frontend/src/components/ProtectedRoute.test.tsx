import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import type { User } from "../types";
import ProtectedRoute from "./ProtectedRoute";

vi.mock("../contexts/AuthContext", () => ({ useAuth: vi.fn() }));
import { useAuth } from "../contexts/AuthContext";

const user: User = {
  id: "1", email: "a@example.com", username: "alice", full_name: "Alice", role: "EDITOR",
  is_active: true, created_at: "2026-01-01T00:00:00Z",
};
const auth = (over: { user: User | null; loading: boolean }) =>
  vi.mocked(useAuth).mockReturnValue({ ...over, login: vi.fn(), register: vi.fn(), logout: vi.fn() });

function renderApp() {
  return render(
    <MemoryRouter initialEntries={["/secret"]}>
      <Routes>
        <Route path="/login" element={<div>login page</div>} />
        <Route element={<ProtectedRoute />}>
          <Route path="/secret" element={<div>secret page</div>} />
        </Route>
      </Routes>
    </MemoryRouter>
  );
}

describe("ProtectedRoute", () => {
  it("shows a spinner while the session is being restored", () => {
    auth({ user: null, loading: true });
    renderApp();
    expect(screen.getByLabelText("Loading")).toBeInTheDocument();
    expect(screen.queryByText("secret page")).not.toBeInTheDocument();
  });
  it("sends anonymous visitors to the login page", () => {
    auth({ user: null, loading: false });
    renderApp();
    expect(screen.getByText("login page")).toBeInTheDocument();
  });
  it("lets signed-in users through", () => {
    auth({ user, loading: false });
    renderApp();
    expect(screen.getByText("secret page")).toBeInTheDocument();
  });
});
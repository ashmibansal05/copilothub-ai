
import { api } from "./api";
import type {
  HealthResponse,
  RegisterPayload,
  TokenResponse,
  User,
} from "../types";

export const authService = {
  // Register a new user
  register: (payload: RegisterPayload) =>
    api
      .post<User>("/auth/register", payload)
      .then((r) => r.data),

  // Authenticate user and receive JWT token
  login: (email: string, password: string) =>
    api
      .post<TokenResponse>("/auth/login", {
        email,
        password,
      })
      .then((r) => r.data),

  // Get currently authenticated user
  me: () =>
    api
      .get<User>("/auth/me")
      .then((r) => r.data),

  // Logout current user
  logout: () =>
    api.post("/auth/logout"),

  // Check backend health
  health: () =>
    api
      .get<HealthResponse>("/health")
      .then((r) => r.data),

  // ========================================================
  // Phase 15: Change Password
  // ========================================================

  changePassword: (
    current_password: string,
    new_password: string
  ) =>
    api
      .post<TokenResponse>("/auth/change-password", {
        current_password,
        new_password,
      })
      .then((r) => r.data),
};
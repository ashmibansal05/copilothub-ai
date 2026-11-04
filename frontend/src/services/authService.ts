import { api } from "./api";
import type { HealthResponse, RegisterPayload, TokenResponse, User } from "../types";

export const authService = {
  register: (payload: RegisterPayload) =>
    api.post<User>("/auth/register", payload).then((r) => r.data),

  login: (email: string, password: string) =>
    api.post<TokenResponse>("/auth/login", { email, password }).then((r) => r.data),

  me: () => api.get<User>("/auth/me").then((r) => r.data),

  logout: () => api.post("/auth/logout"),

  health: () => api.get<HealthResponse>("/health").then((r) => r.data),
};
import { api } from "./api";
import type {
  ControlAction,
  InvitePreview,
  SessionDetail,
  SessionEvent,
  SessionSummary,
} from "../types";

export const sessionService = {
  list: () => api.get<SessionSummary[]>("/sessions").then((r) => r.data),

  create: (name: string, task: string) =>
    api.post<SessionDetail>("/sessions", { name, task }).then((r) => r.data),

  get: (id: string) => api.get<SessionDetail>(`/sessions/${id}`).then((r) => r.data),

  preview: (code: string) =>
    api.get<InvitePreview>(`/sessions/invite/${encodeURIComponent(code)}`).then((r) => r.data),

  join: (code: string) => api.post<SessionDetail>("/sessions/join", { code }).then((r) => r.data),

  events: (id: string) => api.get<SessionEvent[]>(`/sessions/${id}/events`).then((r) => r.data),

  control: (id: string, action: ControlAction) =>
    api.post(`/sessions/${id}/${action}`).then((r) => r.data),
};
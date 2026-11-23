
import { api } from "./api";

import type {
  AgentState,
  ControlAction,
  Intervention,
  InterventionPayload,
  InvitePreview,
  MemoryView,
  SessionDetail,
  SessionEvent,
  SessionSummary,
  ChunkInfo,
  DocumentInfo,
  SearchHit,
} from "../types";

export const sessionService = {
  // ============================================================
  // Existing Session Management
  // ============================================================

  list: () =>
    api.get<SessionSummary[]>("/sessions").then((r) => r.data),

  create: (name: string, task: string) =>
    api.post<SessionDetail>("/sessions", { name, task }).then((r) => r.data),

  get: (id: string) =>
    api.get<SessionDetail>(`/sessions/${id}`).then((r) => r.data),

  preview: (code: string) =>
    api
      .get<InvitePreview>(`/sessions/invite/${encodeURIComponent(code)}`)
      .then((r) => r.data),

  join: (code: string) =>
    api.post<SessionDetail>("/sessions/join", { code }).then((r) => r.data),

  events: (id: string) =>
    api.get<SessionEvent[]>(`/sessions/${id}/events`).then((r) => r.data),

  state: (id: string) =>
    api.get<AgentState>(`/sessions/${id}/state`).then((r) => r.data),

  control: (id: string, action: ControlAction) =>
    api.post(`/sessions/${id}/${action}`).then((r) => r.data),

  // ============================================================
  // Phase 7: Human Interventions
  // ============================================================

  interventions: (id: string) =>
    api
      .get<Intervention[]>(`/sessions/${id}/interventions`)
      .then((r) => r.data),

  intervene: (id: string, payload: InterventionPayload) =>
    api
      .post<Intervention>(`/sessions/${id}/interventions`, payload)
      .then((r) => r.data),

  // ============================================================
  // Phase 8: Constraints and Memory
  // ============================================================

  removeConstraint: (id: string, constraintId: string) =>
    api
      .delete(`/sessions/${id}/constraints/${constraintId}`)
      .then((r) => r.data),

  memory: (id: string) =>
    api.get<MemoryView>(`/sessions/${id}/memory`).then((r) => r.data),

  // ============================================================
  // Phase 9: Conflict Resolution
  // ============================================================

  resolveConflict: (
    id: string,
    conflictId: string,
    winnerConstraintId: string | null
  ) =>
    api
      .post(`/sessions/${id}/conflicts/${conflictId}/resolve`, {
        winner_constraint_id: winnerConstraintId,
      })
      .then((r) => r.data),

  // ============================================================
  // Phase 10: Document Management and RAG
  // ============================================================

  documents: (id: string) =>
    api.get<DocumentInfo[]>(`/sessions/${id}/documents`).then((r) => r.data),

  uploadDocument: (
    id: string,
    file: File,
    meta: {
      source_name: string;
      source_type: string;
    }
  ) => {
    const form = new FormData();

    form.append("file", file);
    form.append("source_name", meta.source_name);
    form.append("source_type", meta.source_type);

    return api
      .post<DocumentInfo>(`/sessions/${id}/documents`, form)
      .then((r) => r.data);
  },

  deleteDocument: (id: string, documentId: string) =>
    api
      .delete(`/sessions/${id}/documents/${documentId}`)
      .then(() => undefined),

  documentChunks: (id: string, documentId: string, limit = 3) =>
    api
      .get<ChunkInfo[]>(
        `/sessions/${id}/documents/${documentId}/chunks`,
        {
          params: { limit },
        }
      )
      .then((r) => r.data),

  searchDocuments: (id: string, query: string) =>
    api
      .post<SearchHit[]>(`/sessions/${id}/documents/search`, {
        query,
        k: 5,
      })
      .then((r) => r.data),
};

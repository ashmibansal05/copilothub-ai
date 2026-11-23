
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
  InstructionResult,
  ReportDetail,
  ReportSummary,

  // Phase 13 and 14
  AnalyticsOverview,
  MLStatus,
  RiskEstimate,
  SessionAnalytics,

  // Phase 15
  Conflict,
  NLPStatus,
  SourceLog,
  SystemStatus,
  ToolExecutionRow,
} from "../types";

export const sessionService = {
  // ============================================================
  // Existing Session Management
  // ============================================================

  list: () =>
    api.get<SessionSummary[]>("/sessions").then((r) => r.data),

  create: (name: string, task: string) =>
    api
      .post<SessionDetail>("/sessions", { name, task })
      .then((r) => r.data),

  get: (id: string) =>
    api
      .get<SessionDetail>(`/sessions/${id}`)
      .then((r) => r.data),

  preview: (code: string) =>
    api
      .get<InvitePreview>(
        `/sessions/invite/${encodeURIComponent(code)}`
      )
      .then((r) => r.data),

  join: (code: string) =>
    api
      .post<SessionDetail>("/sessions/join", { code })
      .then((r) => r.data),

  events: (id: string) =>
    api
      .get<SessionEvent[]>(`/sessions/${id}/events`)
      .then((r) => r.data),

  state: (id: string) =>
    api
      .get<AgentState>(`/sessions/${id}/state`)
      .then((r) => r.data),

  control: (id: string, action: ControlAction) =>
    api
      .post(`/sessions/${id}/${action}`)
      .then((r) => r.data),

  // ============================================================
  // Phase 7: Human Interventions
  // ============================================================

  interventions: (id: string) =>
    api
      .get<Intervention[]>(`/sessions/${id}/interventions`)
      .then((r) => r.data),

  intervene: (id: string, payload: InterventionPayload) =>
    api
      .post<Intervention>(
        `/sessions/${id}/interventions`,
        payload
      )
      .then((r) => r.data),

  // ============================================================
  // Phase 8: Constraints and Memory
  // ============================================================

  removeConstraint: (id: string, constraintId: string) =>
    api
      .delete(`/sessions/${id}/constraints/${constraintId}`)
      .then((r) => r.data),

  memory: (id: string) =>
    api
      .get<MemoryView>(`/sessions/${id}/memory`)
      .then((r) => r.data),

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
    api
      .get<DocumentInfo[]>(`/sessions/${id}/documents`)
      .then((r) => r.data),

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

  documentChunks: (
    id: string,
    documentId: string,
    limit = 3
  ) =>
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

  // ============================================================
  // Phase 11: Saved Reports
  // ============================================================

  reports: (id: string) =>
    api
      .get<ReportSummary[]>(`/sessions/${id}/reports`)
      .then((r) => r.data),

  report: (id: string, reportId: string) =>
    api
      .get<ReportDetail>(
        `/sessions/${id}/reports/${reportId}`
      )
      .then((r) => r.data),

  // ============================================================
  // Phase 12: Natural-Language Instructions
  // ============================================================

  instruct: (id: string, text: string) =>
    api
      .post<InstructionResult>(
        `/sessions/${id}/instructions`,
        { text }
      )
      .then((r) => r.data),

  // ============================================================
  // Phase 13: ML Intervention-Risk Prediction
  // ============================================================

  risk: (id: string) =>
    api
      .get<RiskEstimate>(`/sessions/${id}/risk`)
      .then((r) => r.data),

  mlStatus: () =>
    api
      .get<MLStatus>("/ml/status")
      .then((r) => r.data),

  // ============================================================
  // Phase 14: Final Research Reports
  // ============================================================

  finalReport: (id: string) =>
    api
      .get<ReportDetail>(`/sessions/${id}/report`)
      .then((r) => r.data),

  generateReport: (id: string) =>
    api
      .post(`/sessions/${id}/report/generate`)
      .then((r) => r.data),

  /**
   * Downloads require JWT authentication.
   * Fetch the file as a blob and save it locally.
   */
  downloadReport: async (
    id: string,
    reportId: string,
    format: "md" | "html" | "docx"
  ) => {
    const response = await api.get(
      `/sessions/${id}/reports/${reportId}/download`,
      {
        params: { format },
        responseType: "blob",
      }
    );

    const url = URL.createObjectURL(
      response.data as Blob
    );

    const link = document.createElement("a");

    link.href = url;
    link.download = `report.${format}`;

    document.body.appendChild(link);
    link.click();
    link.remove();

    URL.revokeObjectURL(url);
  },

  // ============================================================
  // Phase 14: Analytics
  // ============================================================

  sessionAnalytics: (id: string) =>
    api
      .get<SessionAnalytics>(
        `/sessions/${id}/analytics`
      )
      .then((r) => r.data),

  analyticsOverview: () =>
    api
      .get<AnalyticsOverview>("/analytics/overview")
      .then((r) => r.data),

  // ============================================================
  // Phase 15: Conflicts and Session Records
  // ============================================================

  conflicts: (id: string) =>
    api
      .get<Conflict[]>(`/sessions/${id}/conflicts`)
      .then((r) => r.data),

  sources: (id: string) =>
    api
      .get<SourceLog[]>(`/sessions/${id}/sources`)
      .then((r) => r.data),

  toolExecutions: (id: string) =>
    api
      .get<ToolExecutionRow[]>(`/sessions/${id}/tools`)
      .then((r) => r.data),

  // ============================================================
  // Phase 15: Session Deletion
  // ============================================================

  deleteSession: (id: string) =>
    api
      .delete(`/sessions/${id}`)
      .then(() => undefined),

  // ============================================================
  // Phase 15: System and NLP Status
  // ============================================================

  systemStatus: () =>
    api
      .get<SystemStatus>("/system/status")
      .then((r) => r.data),

  nlpStatus: () =>
    api
      .get<NLPStatus>("/nlp/status")
      .then((r) => r.data),
};
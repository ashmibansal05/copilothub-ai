import { api } from "./api";

export interface CodeArtifact {
  id: string; path: string; language: string; version: number;
  validation_status: string; updated_at?: string;
}
export interface CodeFile extends CodeArtifact {
  content: string; validation_details: string; created_at?: string;
}
export interface CodeVersion { version: number; origin: string; validation_status: string; created_at: string; }

async function download(path: string, fallback: string) {
  const response = await api.get(path, { responseType: "blob", timeout: 120000 });
  const url = URL.createObjectURL(response.data as Blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = fallback;
  document.body.appendChild(anchor);
  anchor.click(); anchor.remove();
  URL.revokeObjectURL(url);
}

export interface CodeReview {
  status: "NONE" | "PENDING" | "APPROVED" | "REJECTED" | "EXPIRED";
  approval_id: string | null;
  versions: Record<string, number>;
  note?: string | null;
}

export const codeService = {
  review: (sid: string) => api.get<CodeReview>(`/sessions/${sid}/code-review`).then(r => r.data),
  requestReview: (sid: string) => api.post<CodeReview>(`/sessions/${sid}/code-review/request`).then(r => r.data),
  decideReview: (sid: string, approve: boolean, feedback: string) =>
    api.post<CodeReview>(`/sessions/${sid}/code-review/decision`, { approve, feedback }).then(r => r.data),
  list: (sid: string) => api.get<{ files: CodeArtifact[]; task_type: string; generating: boolean }>(`/sessions/${sid}/code`).then(r => r.data),
  file: (sid: string, aid: string, version?: number) => api.get<CodeFile>(`/sessions/${sid}/code/${aid}`, { params: { version } }).then(r => r.data),
  versions: (sid: string, aid: string) => api.get<CodeVersion[]>(`/sessions/${sid}/code/${aid}/versions`).then(r => r.data),
  update: (sid: string, aid: string, content: string, expected_version: number) => api.put(`/sessions/${sid}/code/${aid}`, { content, expected_version }).then(r => r.data),
  generate: (sid: string, instruction: string) => api.post(`/sessions/${sid}/code/generate`, { instruction }).then(r => r.data),
  downloadFile: (sid: string, aid: string, name: string) => download(`/sessions/${sid}/code/${aid}/download`, name),
  downloadZip: (sid: string, complete = false) => download(`/sessions/${sid}/code-export?complete=${complete}`, complete ? "complete-project.zip" : "source-code.zip"),
};

import { ClientError, type ApiError } from "@/lib/types";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  if (init?.body && !(init.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const response = await fetch(path, { ...init, headers });
  if (response.status === 204) {
    return undefined as T;
  }
  const payload = (await response.json().catch(() => null)) as T | ApiError | null;
  if (!response.ok) {
    throw new ClientError(response.status, payload as ApiError | null, response.statusText);
  }
  return payload as T;
}

export const api = {
  register(email: string, password: string) {
    return request<{ user: { email: string } }>("/api/auth/register", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    });
  },
  login(email: string, password: string) {
    return request<{ user: { email: string } }>("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    });
  },
  logout() {
    return request<void>("/api/auth/logout", { method: "POST" });
  },
  me() {
    return request<import("@/lib/types").User>("/api/auth/me");
  },
  documents() {
    return request<{ items: import("@/lib/types").DocumentItem[]; total: number }>("/api/backend/documents");
  },
  document(id: string) {
    return request<import("@/lib/types").DocumentItem>(`/api/backend/documents/${id}`);
  },
  upload(file: File) {
    const body = new FormData();
    body.set("file", file);
    return request<import("@/lib/types").DocumentItem>("/api/backend/documents", { method: "POST", body });
  },
  removeDocument(id: string) {
    return request<void>(`/api/backend/documents/${id}`, { method: "DELETE" });
  },
  reprocess(id: string) {
    return request<import("@/lib/types").DocumentItem>(`/api/backend/documents/${id}/reprocess`, {
      method: "POST",
    });
  },
  conversations() {
    return request<import("@/lib/types").Conversation[]>("/api/backend/conversations");
  },
  conversation(id: string) {
    return request<import("@/lib/types").Conversation>(`/api/backend/conversations/${id}`);
  },
  ask(body: { message: string; conversation_id?: string; document_ids?: string[]; provider?: string }) {
    return request<import("@/lib/types").ChatResponse>("/api/backend/chat", {
      method: "POST",
      body: JSON.stringify(body),
    });
  },
  runs() {
    return request<{ items: import("@/lib/types").AgentRun[] }>("/api/backend/agent/runs");
  },
  run(id: string) {
    return request<import("@/lib/types").AgentRun>(`/api/backend/agent/runs/${id}`);
  },
  startRun(body: { task: string; document_ids: string[]; provider?: string }) {
    return request<import("@/lib/types").AgentRun>("/api/backend/agent/runs", {
      method: "POST",
      body: JSON.stringify(body),
    });
  },
  summary() {
    return request<import("@/lib/types").MetricsSummary>("/api/backend/metrics/summary");
  },
  timeseries() {
    return request<import("@/lib/types").UsagePoint[]>("/api/backend/metrics/timeseries");
  },
  usage(status?: string) {
    const query = status ? `?status=${encodeURIComponent(status)}` : "";
    return request<{ items: import("@/lib/types").UsageRow[] }>(`/api/backend/metrics/usage${query}`);
  },
  activity(action?: string) {
    const query = action ? `?action=${encodeURIComponent(action)}` : "";
    return request<{ items: import("@/lib/types").ActivityRow[] }>(`/api/backend/metrics/activity${query}`);
  },
};

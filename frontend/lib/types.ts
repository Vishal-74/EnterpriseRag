export type User = {
  id: string;
  email: string;
  created_at: string;
};

export type ApiError = {
  error: {
    code: string;
    message: string;
    request_id?: string;
    document_id?: string;
    document_status?: string;
    details?: unknown;
  };
};

export type DocumentItem = {
  id: string;
  original_filename: string;
  kind: string;
  content_type: string;
  size_bytes: number;
  sha256: string;
  status: "pending" | "processing" | "ready" | "failed";
  error_message: string | null;
  chunk_count: number;
  created_at: string;
  updated_at: string;
  chunks: ChunkPreview[];
};

export type ChunkPreview = {
  id: string;
  chunk_index: number;
  page_start: number | null;
  page_end: number | null;
  section: string | null;
  row_start: number | null;
  row_end: number | null;
  preview: string;
};

export type Citation = {
  document_id: string;
  document_name: string;
  chunk_id: string;
  page_start: number | null;
  page_end: number | null;
  section: string | null;
  row_start: number | null;
  row_end: number | null;
  snippet: string;
  score: number;
};

export type ChatResponse = {
  conversation_id: string;
  message_id: string;
  answer: string;
  citations: Citation[];
  insufficient_evidence: boolean;
  conflict: boolean;
  conflict_summary: string | null;
  unsupported_claims: string[];
  ungrounded: boolean;
  injection_flags: string[];
  answer_origin: "model" | "retrieval_gate" | "cache";
  provider: string | null;
  model: string | null;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  latency_ms: number;
  history_tokens: number;
  cached: boolean;
};

export type Conversation = {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
  message_count: number;
  summary?: string;
  messages?: Message[];
};

export type Message = {
  id: string;
  role: string;
  content: string;
  citations: Citation[];
  metadata: Record<string, unknown>;
  created_at: string;
};

export type AgentStep = {
  id: string;
  step_index: number;
  tool_name: string;
  tool_input: Record<string, unknown>;
  tool_output: Record<string, unknown> | null;
  latency_ms: number;
  status: string;
  error: string | null;
  created_at: string;
};

export type AgentRun = {
  id: string;
  task: string;
  status: string;
  stop_reason: string | null;
  provider: string | null;
  document_ids: string[];
  final_output: { report?: ReportBody | null; stop_reason?: string } | null;
  error: string | null;
  created_at: string;
  finished_at: string | null;
  steps: AgentStep[];
};

export type ReportBody = {
  title: string;
  summary: string;
  findings: { statement: string; evidence: string[]; source_chunk_ids: string[] }[];
  recommendations: string[];
  gaps: string[];
  degraded?: boolean;
};

export type MetricsSummary = {
  documents: number;
  conversations: number;
  agent_runs: number;
  requests: number;
  total_tokens: number;
  prompt_tokens: number;
  completion_tokens: number;
  estimated_cost_usd: number;
  avg_latency_ms: number;
  p50_latency_ms: number;
  p95_latency_ms: number;
  error_rate: number;
};

export type UsagePoint = {
  day: string;
  model: string;
  provider: string;
  requests: number;
  total_tokens: number;
  avg_latency_ms: number;
  errors: number;
};

export type UsageRow = {
  id: string;
  created_at: string;
  provider: string;
  model: string;
  operation: string;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  latency_ms: number;
  status: string;
  error: string | null;
  cost_usd: number;
};

export type ActivityRow = {
  id: string;
  created_at: string;
  action: string;
  resource_type: string;
  resource_id: string;
  detail: Record<string, unknown>;
};

export class ClientError extends Error {
  status: number;
  code: string;
  documentId?: string;

  constructor(status: number, body: ApiError | null, fallback: string) {
    super(body?.error.message || fallback);
    this.status = status;
    this.code = body?.error.code || "request_failed";
    this.documentId = body?.error.document_id;
  }
}

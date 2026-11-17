/** Typed client for the InvoiceGuard API. The reviewer's key lives in sessionStorage only. */

export const API_URL: string = import.meta.env.VITE_API_URL ?? "http://localhost:8000";
const KEY = "invoiceguard.apiKey";

export function getApiKey(): string | null {
  try {
    return sessionStorage.getItem(KEY);
  } catch {
    return null;
  }
}

export function setApiKey(key: string | null) {
  try {
    if (key) sessionStorage.setItem(KEY, key);
    else sessionStorage.removeItem(KEY);
  } catch {
    /* storage unavailable: the key lasts for this page only */
  }
}

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  const key = getApiKey();
  if (key) headers.set("X-API-Key", key);
  const response = await fetch(`${API_URL}${path}`, { ...init, headers });
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = await response.json();
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(response.status, detail || `request failed (${response.status})`);
  }
  if (response.headers.get("content-type")?.includes("application/json")) {
    return (await response.json()) as T;
  }
  return (await response.blob()) as T;
}

const json = (body: unknown): RequestInit => ({
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

export type Invoice = {
  id: string;
  invoice_number: string | null;
  vendor_id: string | null;
  po_number: string | null;
  currency: string | null;
  total: string | null;
  status: string;
  version: number;
  created_at: string;
};

export type AuditEvent = {
  id: number;
  event_type: string;
  actor: string;
  payload: Record<string, unknown>;
  duration_ms: number | null;
  created_at: string;
};

export type InvoiceDetail = Invoice & {
  subtotal: string | null;
  tax: string | null;
  trace_id: string | null;
  lines: { line_no: number; sku: string; qty: string; unit_price: string }[];
  approvals: {
    invoice_version: number;
    amount: string;
    reviewer: string;
    decision: string;
    reason: string | null;
    created_at: string;
  }[];
  timeline: AuditEvent[];
  llm_calls: {
    step: string;
    provider: string;
    model: string;
    input_tokens: number;
    output_tokens: number;
    latency_ms: number;
    tokens_per_second: string | null;
    cost_usd: string;
  }[];
};

export type ExtractionField = {
  field: string;
  value: string | null;
  confidence: string;
  page: number | null;
  snippet: string | null;
};

export type FailedJob = {
  id: number;
  invoice_id: string | null;
  task: string;
  error: string;
  attempts: number;
  status: string;
  created_at: string;
};

export type MetricsSummary = {
  invoices_by_status: Record<string, number>;
  decisions: {
    decided: number;
    auto_approved: number;
    needs_review: number;
    rejected: number;
    straight_through_rate: string | null;
    review_rate: string | null;
  };
  exceptions: { reason: string; count: number }[];
  human_workload: { reviewed: number; median_review_seconds: number | null; edits: number };
  llm: {
    provider: string;
    model: string;
    calls: number;
    total_cost_usd: string;
    cost_per_request_usd: string;
    p50_latency_ms: number;
    p95_latency_ms: number;
    avg_tokens_per_second: string | null;
  }[];
  operations: { open_failed_jobs: number; outbox_pending: number };
};

export const api = {
  listInvoices: (status?: string) =>
    request<Invoice[]>(`/invoices?limit=200${status ? `&status=${encodeURIComponent(status)}` : ""}`),
  invoice: (id: string) => request<InvoiceDetail>(`/invoices/${id}`),
  extraction: (id: string) => request<ExtractionField[]>(`/invoices/${id}/extraction`),
  document: (id: string) => request<Blob>(`/invoices/${id}/document`),
  approve: (id: string, version: number, reason: string) =>
    request<Invoice>(`/invoices/${id}/approve`, json({ expected_version: version, reason })),
  reject: (id: string, version: number, reason: string) =>
    request<Invoice>(`/invoices/${id}/reject`, json({ expected_version: version, reason })),
  edit: (id: string, version: number, reason: string, changes: Record<string, string>) =>
    request<Invoice>(`/invoices/${id}/edit`, json({ expected_version: version, reason, changes })),
  post: (id: string) =>
    request<{ outcome: string; idempotency_key: string }>(`/invoices/${id}/post`, { method: "POST" }),
  failedJobs: () => request<FailedJob[]>("/failed-jobs"),
  replay: (id: string) => request<Invoice>(`/invoices/${id}/replay`, { method: "POST" }),
  metrics: () => request<MetricsSummary>("/metrics/summary"),
  upload: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<Invoice>("/documents", { method: "POST", body: form });
  },
};

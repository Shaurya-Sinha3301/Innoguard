/** Typed client for the InvoiceGuard API. The reviewer's key lives in sessionStorage only. */

/** Where the API lives. VITE_API_URL (set at build time) wins; otherwise a page opened on
 * localhost talks to the local API and any other host talks to the hosted demo API. */
const HOSTED_API = "https://invoiceguard-api-rbcd.onrender.com";
const isLocalPage = ["localhost", "127.0.0.1"].includes(globalThis.location?.hostname ?? "localhost");
export const API_URL: string = (
  import.meta.env.VITE_API_URL ?? (isLocalPage ? "http://localhost:8000" : HOSTED_API)
).replace(/\/+$/, "");
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

export type Me = { name: string; kind: "human" | "agent"; scopes: string[]; packs: string[] };

export type PrincipalRow = {
  id: string;
  name: string;
  kind: string;
  scopes: string[];
  packs: string[];
  key_prefix: string;
  disabled: boolean;
  created_by: string;
  last_used_at: string | null;
};

export type Suggestion = {
  id: number;
  case_version: number;
  decision: string;
  rationale: string;
  proposed_by: string;
  status: string;
  resolved_by: string | null;
  created_at: string;
};

export type Grant = {
  id: string;
  case_version: number;
  amount: string;
  issued_by: string;
  expires_at: string;
  used_at: string | null;
  used_by: string | null;
};

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
  pack_id?: string;
  reasons?: string[];
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
  reasons: string[];
  purchase_order: {
    po_number: string;
    vendor_id: string;
    currency: string;
    lines: { sku: string; qty: string; unit_price: string }[];
  } | null;
  receipt_count: number;
  received: Record<string, string>;
  lines: { line_no: number; sku: string; qty: string; unit_price: string }[];
  approvals: {
    case_version: number;
    amount: string;
    reviewer: string;
    decision: string;
    reason: string | null;
    created_at: string;
  }[];
  timeline: AuditEvent[];
  data?: Record<string, string>;
  context?: ExpenseContext;
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

export type ExpenseContext = {
  employee?: { employee_id: string; name: string; card_last4: string } | null;
  category?: { category: string; cap: string; blocked: boolean } | null;
  card_transaction?: { txn_id: string; merchant: string; txn_date: string; amount: string; currency: string; clean: boolean } | null;
  claim?: { employee_id: string; merchant: string; expense_date: string; card_last4: string; category: string; total: string; currency: string };
  submitted_on?: string;
  max_auto_amount?: string;
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
  case_id: string | null;
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

import type { Manifest } from "./pack";

export const api = {
  packs: () => request<{ id: string; name: string; description: string }[]>("/packs"),
  pack: (id: string) => request<Manifest>(`/packs/${id}`),
  listCases: (pack: string, status?: string) =>
    request<Invoice[]>(`/cases?limit=200&pack=${encodeURIComponent(pack)}${status ? `&status=${encodeURIComponent(status)}` : ""}`),
  caseDetail: (id: string) => request<InvoiceDetail>(`/cases/${id}`),
  me: () => request<Me>("/me"),
  suggestions: (id: string) => request<Suggestion[]>(`/invoices/${id}/suggestions`),
  dismissSuggestion: (id: string, suggestionId: number) =>
    request<Suggestion>(`/invoices/${id}/suggestions/${suggestionId}/dismiss`, { method: "POST" }),
  grants: (id: string) => request<Grant[]>(`/invoices/${id}/grants`),
  issueGrant: (id: string, ttlMinutes: number) =>
    request<Grant>(`/invoices/${id}/grants`, json({ ttl_minutes: ttlMinutes })),
  principals: () => request<PrincipalRow[]>("/principals"),
  createPrincipal: (body: { name: string; kind: "agent" | "human"; scopes: string[]; packs?: string[] }) =>
    request<PrincipalRow & { key: string }>("/principals", json(body)),
  disablePrincipal: (id: string) => request<PrincipalRow>(`/principals/${id}/disable`, { method: "POST" }),
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
  metrics: (pack?: string) => request<MetricsSummary>(`/metrics/summary${pack ? `?pack=${encodeURIComponent(pack)}` : ""}`),
  upload: (file: File, pack = "invoices") => {
    const form = new FormData();
    form.append("file", file);
    return request<Invoice>(`/documents?pack=${encodeURIComponent(pack)}`, { method: "POST", body: form });
  },
};

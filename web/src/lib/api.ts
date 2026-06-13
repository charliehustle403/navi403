/**
 * Typed fetch client for the Navi API. TS mirrors of the Pydantic contracts in
 * `src/navi/contracts.py` — field names stay snake_case (the wire format); no remapping layer.
 *
 * Served same-origin by FastAPI's mount_spa in production; `npm run dev` proxies these
 * paths to 127.0.0.1:8000 (see vite.config.ts).
 */

export type Route = "answer_inline" | "sap_review" | "research" | "clarify" | "refuse";

/** POST /ask response (contracts.StructuredResult). */
export interface StructuredResult {
  run_id: string;
  route: string; // one of Route in practice; server type is plain str
  answer: string;
  evidence: string[];
  cost_usd: number;
  needs_approval: boolean;
  truncated: boolean; // run stopped on budget — surface as a warning chip
}

/** One trace event in GET /runs/{id} (contracts.TraceEventView). */
export interface TraceEventView {
  event_type: string; // real wire values: "route" | "model_call" | "broker_decision" | "error"
  tool_name: string | null; // broker_decision only
  route: string | null; // "route" events only (the dispatched route)
  verdict: string | null; // broker_decision: "allowed" | "denied" ("approval_required" reserved)
  tokens_in: number | null; // model_call only
  tokens_out: number | null;
  payload_hash: string | null; // sha256 — NEVER clear text; render as truncated hash
  created_at: string; // ISO-8601
}

/** GET /runs/{id} (contracts.RunTrace). */
export interface RunTrace {
  run_id: string;
  agent_id: string | null;
  route: string | null;
  status: string;
  cost_usd: number;
  started_at: string;
  ended_at: string | null;
  events: TraceEventView[];
}

/** One row of GET /runs (contracts.RunSummary). Unrendered in v1 (history page is v2). */
export interface RunSummary {
  run_id: string;
  agent_id: string | null;
  route: string | null;
  status: string;
  cost_usd: number;
  started_at: string;
  ended_at: string | null;
  tokens_in: number | null; // null = "no token data", NOT zero
  tokens_out: number | null;
}

/** GET /health. */
export interface HealthResponse {
  status: string;
  db: string;
}

/** Non-2xx responses carry FastAPI's `{"detail": ...}` body. */
export class ApiError extends Error {
  readonly status: number;
  readonly detail: string;

  constructor(status: number, detail: string) {
    super(`API ${status}: ${detail}`);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, init);
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body: unknown = await res.json();
      if (body && typeof body === "object" && "detail" in body) {
        detail = String((body as { detail: unknown }).detail);
      }
    } catch {
      // non-JSON error body — keep statusText
    }
    throw new ApiError(res.status, detail);
  }
  return res.json() as Promise<T>;
}

export function ask(text: string): Promise<StructuredResult> {
  return request<StructuredResult>("/ask", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  });
}

export function getRun(runId: string): Promise<RunTrace> {
  return request<RunTrace>(`/runs/${encodeURIComponent(runId)}`);
}

export function listRuns(limit = 50): Promise<RunSummary[]> {
  return request<RunSummary[]>(`/runs?limit=${limit}`);
}

export function getHealth(): Promise<HealthResponse> {
  return request<HealthResponse>("/health");
}

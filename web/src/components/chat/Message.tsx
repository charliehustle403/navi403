import { EvidenceChip } from "@/components/chat/EvidenceChip";
import { RouteBadge } from "@/components/chat/RouteBadge";
import type { StructuredResult } from "@/lib/api";

export interface ChatMessage {
  id: number;
  role: "user" | "navi";
  text: string;
  /** Navi messages carry the full result for badges/evidence/cost. */
  result?: StructuredResult;
  /** Set instead of result when the ask failed. */
  error?: string;
}

export function Message({ message }: { message: ChatMessage }) {
  if (message.role === "user") {
    return (
      <div className="flex justify-end">
        <div className="glass max-w-[85%] rounded-lg rounded-br-sm px-3.5 py-2.5 text-sm whitespace-pre-wrap">
          {message.text}
        </div>
      </div>
    );
  }

  if (message.error !== undefined) {
    return (
      <div className="glass max-w-[92%] rounded-lg border-danger/40 px-3.5 py-2.5">
        <span className="readout text-[9px] uppercase tracking-[0.15em] text-danger">
          Transmission failed
        </span>
        <p className="mt-1 text-sm text-muted-foreground">{message.error}</p>
      </div>
    );
  }

  const r = message.result;
  return (
    <div className="glass max-w-[92%] rounded-lg rounded-bl-sm px-3.5 py-2.5">
      {r && (
        <div className="mb-1.5 flex flex-wrap items-center gap-1.5">
          <RouteBadge route={r.route} />
          {r.truncated && (
            <span className="readout rounded border border-warn/30 bg-warn/15 px-1.5 py-0.5 text-[9px] uppercase tracking-[0.15em] text-warn">
              budget-truncated
            </span>
          )}
          {r.needs_approval && (
            <span className="readout rounded border border-warn/30 bg-warn/15 px-1.5 py-0.5 text-[9px] uppercase tracking-[0.15em] text-warn">
              approval required
            </span>
          )}
        </div>
      )}
      <p className="text-sm whitespace-pre-wrap">{message.text}</p>
      {r && (
        <div className="mt-2 flex flex-wrap items-center gap-3">
          <EvidenceChip evidence={r.evidence} />
          <span className="readout ml-auto text-[10px] text-muted-foreground">
            ${r.cost_usd.toFixed(4)}
          </span>
        </div>
      )}
    </div>
  );
}

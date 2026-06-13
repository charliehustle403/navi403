import { RouteBadge } from "@/components/chat/RouteBadge";
import type { TraceEventView } from "@/lib/api";

function timeOf(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "--:--:--" : d.toTimeString().slice(0, 8);
}

function shortHash(hash: string): string {
  return `#${hash.slice(0, 8)}…`;
}

const HASH_TITLE = "hashed payload (sha256) — raw content is never stored";

/**
 * One trace event. Wire shapes (src/navi/trace.py): event_type is
 * "route" | "model_call" | "broker_decision" | "error"; deny reasons and redaction
 * labels arrive ONLY as sha256 hashes — rendered as truncated hashes, never invented text.
 * Redaction is detected as verdict==="allowed" with a non-null payload_hash.
 */
export function TraceEventRow({ event }: { event: TraceEventView }) {
  const time = (
    <span className="readout shrink-0 text-[9px] text-muted-foreground/60">
      {timeOf(event.created_at)}
    </span>
  );

  if (event.event_type === "route") {
    return (
      <li className="flex items-center gap-2 py-1.5">
        {time}
        <span className="readout text-[10px] uppercase text-muted-foreground">route</span>
        {event.route && <RouteBadge route={event.route} />}
      </li>
    );
  }

  if (event.event_type === "model_call") {
    return (
      <li className="flex items-center gap-2 py-1.5">
        {time}
        <span className="readout text-[10px] uppercase text-muted-foreground">model call</span>
        <span className="readout ml-auto text-[10px] text-foreground">
          {event.tokens_in ?? "–"} → {event.tokens_out ?? "–"} tok
        </span>
      </li>
    );
  }

  if (event.event_type === "broker_decision") {
    const redacted = event.verdict === "allowed" && event.payload_hash !== null;
    const denied = event.verdict === "denied";
    const reserved = event.verdict !== null && event.verdict !== "allowed" && !denied;
    return (
      <li className="flex items-center gap-2 py-1.5">
        {time}
        <span
          className={`readout text-[12px] ${
            denied ? "text-danger" : redacted || reserved ? "text-warn" : "text-ok"
          }`}
          title={
            denied
              ? "broker denied this tool call"
              : redacted
                ? "allowed — output redacted before reaching the model"
                : reserved
                  ? `verdict: ${event.verdict}`
                  : "broker allowed this tool call"
          }
        >
          {denied ? "✗" : redacted ? "⛨" : reserved ? "⚠" : "✓"}
        </span>
        <span className="readout text-[10px] text-foreground">{event.tool_name ?? "tool"}</span>
        {redacted && (
          <span className="readout text-[9px] uppercase tracking-[0.1em] text-warn">
            output redacted
          </span>
        )}
        {denied && (
          <span className="readout text-[9px] uppercase tracking-[0.1em] text-danger">denied</span>
        )}
        {event.payload_hash && (
          <span
            className="readout ml-auto text-[9px] text-muted-foreground/60"
            title={HASH_TITLE}
          >
            {shortHash(event.payload_hash)}
          </span>
        )}
      </li>
    );
  }

  // "error" (and anything unknown): red row + hash if present.
  return (
    <li className="flex items-center gap-2 py-1.5">
      {time}
      <span className="readout text-[10px] uppercase text-danger">{event.event_type}</span>
      {event.payload_hash && (
        <span className="readout ml-auto text-[9px] text-muted-foreground/60" title={HASH_TITLE}>
          {shortHash(event.payload_hash)}
        </span>
      )}
    </li>
  );
}

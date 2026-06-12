import { RouteBadge } from "@/components/chat/RouteBadge";
import { TotalsRow } from "@/components/inspector/TotalsRow";
import { TraceTimeline } from "@/components/inspector/TraceTimeline";
import type { RunTrace } from "@/lib/api";

/**
 * The HUD diagnostics panel: the selected run's trace, verdicts, and totals.
 * Step 3 adds the TIMELINE | GRAPH tabs here.
 */
export function InspectorPane({
  trace,
  error,
}: {
  trace: RunTrace | null;
  error: string | null;
}) {
  return (
    <div className="flex min-h-0 flex-1 flex-col p-4">
      <div className="flex items-center justify-between">
        <h2 className="readout text-[10px] uppercase tracking-[0.3em] text-muted-foreground">
          Run Inspector
        </h2>
        {trace?.route && <RouteBadge route={trace.route} />}
      </div>

      {error !== null ? (
        <div className="flex flex-1 items-center justify-center">
          <p className="readout text-xs text-danger">{error}</p>
        </div>
      ) : trace === null ? (
        <div className="flex flex-1 items-center justify-center">
          <p className="readout text-xs text-muted-foreground/60">AWAITING RUN DATA</p>
        </div>
      ) : (
        <>
          <p className="readout mt-1 truncate text-[9px] text-muted-foreground/60" title={trace.run_id}>
            run {trace.run_id} · {trace.status}
          </p>
          <div className="mt-2 min-h-0 flex-1 overflow-y-auto">
            <TraceTimeline events={trace.events} />
          </div>
          <TotalsRow trace={trace} />
        </>
      )}
    </div>
  );
}

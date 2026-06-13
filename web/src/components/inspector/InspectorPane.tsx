import { useState } from "react";

import { RouteBadge } from "@/components/chat/RouteBadge";
import { RunGraph } from "@/components/inspector/RunGraph";
import { TotalsRow } from "@/components/inspector/TotalsRow";
import { TraceTimeline } from "@/components/inspector/TraceTimeline";
import type { RunTrace } from "@/lib/api";

type Tab = "timeline" | "graph";

/**
 * The HUD diagnostics panel: the selected run's trace as a TIMELINE or a GRAPH.
 * Both render from the same RunTrace already in memory — switching tabs never refetches.
 */
export function InspectorPane({
  trace,
  error,
}: {
  trace: RunTrace | null;
  error: string | null;
}) {
  const [tab, setTab] = useState<Tab>("timeline");

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
          <p
            className="readout mt-1 truncate text-[9px] text-muted-foreground/60"
            title={trace.run_id}
          >
            run {trace.run_id} · {trace.status}
          </p>

          {/* Tabs */}
          <div className="mt-2 flex gap-1">
            {(["timeline", "graph"] as const).map((t) => (
              <button
                key={t}
                type="button"
                onClick={() => setTab(t)}
                className={`readout rounded px-2 py-1 text-[9px] uppercase tracking-[0.2em] transition-colors ${
                  tab === t
                    ? "bg-primary/15 text-primary"
                    : "text-muted-foreground hover:text-foreground"
                }`}
              >
                {t}
              </button>
            ))}
          </div>

          <div className="mt-2 min-h-0 flex-1 overflow-y-auto">
            {tab === "timeline" ? (
              <TraceTimeline events={trace.events} />
            ) : (
              <div className="h-full min-h-[260px]">
                <RunGraph trace={trace} />
              </div>
            )}
          </div>

          <TotalsRow trace={trace} />
        </>
      )}
    </div>
  );
}

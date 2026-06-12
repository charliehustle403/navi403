import type { RunTrace } from "@/lib/api";
import { BUDGET_REFERENCE_USD } from "@/lib/constants";

/** Token totals + cost vs the reference budget (HUD meter). */
export function TotalsRow({ trace }: { trace: RunTrace }) {
  const tokensIn = trace.events.reduce((n, e) => n + (e.tokens_in ?? 0), 0);
  const tokensOut = trace.events.reduce((n, e) => n + (e.tokens_out ?? 0), 0);
  const pct = Math.min(100, (trace.cost_usd / BUDGET_REFERENCE_USD) * 100);

  return (
    <div className="space-y-2 border-t border-border pt-3">
      <div className="flex items-center justify-between">
        <span className="readout text-[9px] uppercase tracking-[0.2em] text-muted-foreground">
          tokens
        </span>
        <span className="readout text-[10px] text-foreground">
          {tokensIn.toLocaleString()} in / {tokensOut.toLocaleString()} out
        </span>
      </div>
      <div className="flex items-center justify-between">
        <span className="readout text-[9px] uppercase tracking-[0.2em] text-muted-foreground">
          cost
        </span>
        <span className="readout text-[10px] text-foreground">
          ${trace.cost_usd.toFixed(4)}{" "}
          <span className="text-muted-foreground/60">of ${BUDGET_REFERENCE_USD.toFixed(2)} ref</span>
        </span>
      </div>
      <div className="h-1 overflow-hidden rounded-full bg-muted">
        <div
          className={`h-full rounded-full transition-all ${pct >= 90 ? "bg-danger" : pct >= 60 ? "bg-warn" : "bg-primary"}`}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}

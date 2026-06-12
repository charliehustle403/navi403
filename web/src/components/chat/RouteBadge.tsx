import { ROUTE_COLORS } from "@/lib/constants";

const FALLBACK = "bg-muted text-muted-foreground border-border";

/** Route chip — distinct color per route, legible in both themes. */
export function RouteBadge({ route }: { route: string }) {
  return (
    <span
      className={`readout inline-block rounded border px-1.5 py-0.5 text-[9px] uppercase tracking-[0.15em] ${ROUTE_COLORS[route] ?? FALLBACK}`}
    >
      {route.replace("_", " ")}
    </span>
  );
}

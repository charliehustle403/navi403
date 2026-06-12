export type OrbState = "idle" | "active" | "error";

/**
 * The arc-reactor orb — Navi's identity element and run-state indicator.
 * CSS-only (rings + core in index.css): idle pulse, faster spin while a run is
 * in flight, red shift on error/refuse.
 */
export function Orb({ state = "idle", size = 220 }: { state?: OrbState; size?: number }) {
  return (
    <div
      className={`orb orb--${state}`}
      style={{ width: size, height: size }}
      aria-hidden="true"
      data-testid="orb"
    >
      <div className="orb__ring orb__ring--outer" />
      <div className="orb__ring orb__ring--mid" />
      <div className="orb__ring orb__ring--inner" />
      <div className="orb__core" />
    </div>
  );
}

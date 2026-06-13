import { Orb } from "@/components/Orb";
import { ThemeToggle } from "@/components/ThemeToggle";
import { APP_VERSION } from "@/lib/constants";
import { useHealth, type HealthState } from "@/lib/useHealth";

const DOT_CLASS: Record<HealthState, string> = {
  ok: "bg-ok",
  degraded: "bg-warn",
  down: "bg-danger",
};

const SYS_STATUS: Record<HealthState, string> = {
  ok: "SYS.STATUS: NOMINAL | DB: OK",
  degraded: "SYS.STATUS: DEGRADED | DB: ERROR",
  down: "SYS.STATUS: OFFLINE | API UNREACHABLE",
};

/**
 * HUD header: wordmark + version readout, live health dot (10s poll), SYS.STATUS strip,
 * theme toggle. `showOrb` renders the mini orb once the boot screen has yielded to a thread.
 */
export function Header({ showOrb = false, orbActive = false }: { showOrb?: boolean; orbActive?: boolean }) {
  const health = useHealth();

  return (
    <header className="glass flex items-center gap-4 rounded-lg px-4 py-2.5">
      <div className="flex items-center gap-3">
        {showOrb && <Orb size={28} state={orbActive ? "active" : "idle"} />}
        <span className="text-lg font-semibold tracking-[0.25em] text-foreground">NAVI</span>
        <span className="readout text-[10px] text-muted-foreground">
          V{APP_VERSION} // ONLINE
        </span>
      </div>

      <div className="readout hidden flex-1 text-center text-[10px] text-muted-foreground sm:block">
        {SYS_STATUS[health]}
      </div>

      <div className="ml-auto flex items-center gap-3">
        <span className="flex items-center gap-1.5">
          <span className={`status-dot ${DOT_CLASS[health]}`} />
          <span className="readout text-[10px] uppercase text-muted-foreground">
            {health === "ok" ? "Online" : health === "degraded" ? "Degraded" : "Offline"}
          </span>
        </span>
        <ThemeToggle />
      </div>
    </header>
  );
}

import { useEffect, useState } from "react";

import { getHealth } from "@/lib/api";

export type HealthState = "ok" | "degraded" | "down";

/** Poll GET /health; ok = api+db green, degraded = api up but db not ok, down = unreachable. */
export function useHealth(intervalMs = 10_000): HealthState {
  const [state, setState] = useState<HealthState>("down");

  useEffect(() => {
    let cancelled = false;

    const poll = async () => {
      try {
        const health = await getHealth();
        if (!cancelled) setState(health.db === "ok" ? "ok" : "degraded");
      } catch {
        if (!cancelled) setState("down");
      }
    };

    void poll();
    const id = setInterval(() => void poll(), intervalMs);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [intervalMs]);

  return state;
}

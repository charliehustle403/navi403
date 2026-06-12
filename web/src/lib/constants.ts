// TODO(scope): expose app version via /health, then read it there instead of hardcoding.
export const APP_VERSION = "0.1";

/** Badge classes per route — 5 distinct colors, legible in both themes. */
export const ROUTE_COLORS: Record<string, string> = {
  answer_inline: "bg-primary/15 text-primary border-primary/30",
  research: "bg-violet-500/15 text-violet-400 border-violet-500/30",
  sap_review: "bg-teal-500/15 text-teal-400 border-teal-500/30",
  clarify: "bg-warn/15 text-warn border-warn/30",
  refuse: "bg-danger/15 text-danger border-danger/30",
};

/**
 * The API does not expose max_cost_per_run (it lives in server model profiles).
 * TODO(scope): expose max_cost_per_run in RunTrace and drop this constant.
 */
export const BUDGET_REFERENCE_USD = 0.5;

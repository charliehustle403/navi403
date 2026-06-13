import type { RunTrace } from "@/lib/api";

/**
 * n8n-style run graph: Navi's FIXED topology (ASK -> ROUTER -> MODEL <-> BROKER -> {KB, WEB}
 * -> RESPONSE) with the selected run's trace events overlaid. Custom SVG, fixed layout — no
 * graph library (only ~7 static nodes). Executed nodes/edges glow; broker verdicts color the
 * tool edges (green=allowed, red=denied, amber=output-redacted), same rules as the timeline.
 */

interface ToolStats {
  allowed: number;
  denied: number;
  redacted: number;
}

interface Aggregate {
  route: string | null;
  modelCalls: number;
  tokensIn: number;
  tokensOut: number;
  tools: Record<string, ToolStats>;
  hasError: boolean;
  ended: boolean;
  brokerCalls: number;
}

function aggregate(trace: RunTrace): Aggregate {
  const tools: Record<string, ToolStats> = {};
  let route: string | null = trace.route;
  let modelCalls = 0;
  let tokensIn = 0;
  let tokensOut = 0;
  let hasError = false;
  let brokerCalls = 0;

  for (const e of trace.events) {
    if (e.event_type === "route") {
      if (e.route) route = e.route;
    } else if (e.event_type === "model_call") {
      modelCalls += 1;
      tokensIn += e.tokens_in ?? 0;
      tokensOut += e.tokens_out ?? 0;
    } else if (e.event_type === "broker_decision" && e.tool_name) {
      brokerCalls += 1;
      const t = (tools[e.tool_name] ??= { allowed: 0, denied: 0, redacted: 0 });
      if (e.verdict === "denied") t.denied += 1;
      else if (e.verdict === "allowed" && e.payload_hash !== null) t.redacted += 1;
      else if (e.verdict === "allowed") t.allowed += 1;
    } else if (e.event_type === "error") {
      hasError = true;
    }
  }
  return { route, modelCalls, tokensIn, tokensOut, tools, hasError, brokerCalls, ended: trace.ended_at !== null };
}

const KB_TOOL = "knowledge_base_search";
const WEB_TOOL = "web_search";

const NODE_W = 108;
const NODE_H = 50;

interface Pt {
  cx: number;
  cy: number;
}

const POS = {
  ask: { cx: 64, cy: 200 },
  router: { cx: 212, cy: 200 },
  model: { cx: 360, cy: 200 },
  broker: { cx: 508, cy: 200 },
  kb: { cx: 644, cy: 96 },
  web: { cx: 644, cy: 304 },
  response: { cx: 360, cy: 332 },
} satisfies Record<string, Pt>;

/** Pick the dominant verdict color for a tool edge. */
function toolColor(s: ToolStats | undefined): string {
  if (!s) return "var(--muted-foreground)";
  if (s.denied > 0) return "var(--navi-danger)";
  if (s.redacted > 0) return "var(--navi-warn)";
  if (s.allowed > 0) return "var(--navi-ok)";
  return "var(--muted-foreground)";
}

function toolLabel(s: ToolStats | undefined): string {
  if (!s) return "";
  const parts: string[] = [];
  if (s.allowed) parts.push(`${s.allowed} ok`);
  if (s.redacted) parts.push(`${s.redacted} redacted`);
  if (s.denied) parts.push(`${s.denied} denied`);
  return parts.join(" / ");
}

function Edge({
  from,
  to,
  active,
  color = "var(--primary)",
  label,
}: {
  from: Pt;
  to: Pt;
  active: boolean;
  color?: string;
  label?: string;
}) {
  // Start/end on the node edges (horizontal-ish), not the centers.
  const x1 = from.cx + (to.cx > from.cx ? NODE_W / 2 : to.cx < from.cx ? -NODE_W / 2 : 0);
  const x2 = to.cx + (from.cx > to.cx ? NODE_W / 2 : from.cx < to.cx ? -NODE_W / 2 : 0);
  const y1 = from.cy + (to.cy > from.cy && to.cx === from.cx ? NODE_H / 2 : 0);
  const y2 = to.cy + (from.cy > to.cy && to.cx === from.cx ? NODE_H / 2 : 0);
  const mx = (x1 + x2) / 2;
  const my = (y1 + y2) / 2;
  return (
    <g style={{ opacity: active ? 1 : 0.22 }}>
      <line
        x1={x1}
        y1={y1}
        x2={x2}
        y2={y2}
        stroke={active ? color : "var(--muted-foreground)"}
        strokeWidth={active ? 1.75 : 1}
        strokeDasharray={active ? undefined : "3 3"}
        style={active ? { filter: "drop-shadow(0 0 3px var(--navi-glow))" } : undefined}
      />
      {label && active && (
        <text
          x={mx}
          y={my - 5}
          textAnchor="middle"
          fontSize="9"
          fill="var(--muted-foreground)"
          style={{ fontFamily: "var(--font-mono)" }}
        >
          {label}
        </text>
      )}
    </g>
  );
}

function Node({
  pos,
  label,
  sub,
  active,
  accent = "var(--primary)",
}: {
  pos: Pt;
  label: string;
  sub?: string;
  active: boolean;
  accent?: string;
}) {
  return (
    <g style={{ opacity: active ? 1 : 0.3 }}>
      <rect
        x={pos.cx - NODE_W / 2}
        y={pos.cy - NODE_H / 2}
        width={NODE_W}
        height={NODE_H}
        rx={8}
        fill="var(--navi-panel)"
        stroke={active ? accent : "var(--navi-panel-border)"}
        strokeWidth={active ? 1.5 : 1}
        style={active ? { filter: "drop-shadow(0 0 4px var(--navi-glow))" } : undefined}
      />
      <text
        x={pos.cx}
        y={sub ? pos.cy - 3 : pos.cy + 4}
        textAnchor="middle"
        fontSize="11"
        fontWeight="600"
        fill="var(--foreground)"
        style={{ fontFamily: "var(--font-mono)", letterSpacing: "0.08em" }}
      >
        {label}
      </text>
      {sub && (
        <text
          x={pos.cx}
          y={pos.cy + 12}
          textAnchor="middle"
          fontSize="8.5"
          fill="var(--muted-foreground)"
          style={{ fontFamily: "var(--font-mono)" }}
        >
          {sub}
        </text>
      )}
    </g>
  );
}

export function RunGraph({ trace }: { trace: RunTrace }) {
  const a = aggregate(trace);
  const started = trace.events.length > 0;
  const routed = a.route !== null;
  const modelRan = a.modelCalls > 0;
  const brokerRan = a.brokerCalls > 0;
  const kb = a.tools[KB_TOOL];
  const web = a.tools[WEB_TOOL];

  const tokens = a.modelCalls > 0 ? `${a.tokensIn}->${a.tokensOut} tok` : undefined;
  const responseAccent = a.hasError ? "var(--navi-danger)" : "var(--navi-ok)";

  return (
    <svg viewBox="0 0 710 400" className="h-full w-full" role="img" aria-label="Run graph">
      {/* Edges (under nodes) */}
      <Edge from={POS.ask} to={POS.router} active={started} />
      <Edge
        from={POS.router}
        to={POS.model}
        active={routed}
        label={a.route ? a.route.replace("_", " ") : undefined}
      />
      <Edge from={POS.model} to={POS.broker} active={brokerRan} />
      <Edge from={POS.broker} to={POS.kb} active={!!kb} color={toolColor(kb)} label={toolLabel(kb)} />
      <Edge from={POS.broker} to={POS.web} active={!!web} color={toolColor(web)} label={toolLabel(web)} />
      <Edge from={POS.model} to={POS.response} active={a.ended} color={responseAccent} />

      {/* Nodes */}
      <Node pos={POS.ask} label="ASK" active={started} />
      <Node pos={POS.router} label="ROUTER" sub={a.route ?? undefined} active={routed} />
      <Node
        pos={POS.model}
        label="MODEL"
        sub={a.modelCalls > 0 ? `${a.modelCalls} calls` : undefined}
        active={modelRan}
      />
      <Node
        pos={POS.broker}
        label="BROKER"
        sub={a.brokerCalls > 0 ? `${a.brokerCalls} calls` : undefined}
        active={brokerRan}
      />
      <Node pos={POS.kb} label="KB" sub={kb ? toolLabel(kb) : undefined} active={!!kb} accent={toolColor(kb)} />
      <Node
        pos={POS.web}
        label="WEB"
        sub={web ? toolLabel(web) : undefined}
        active={!!web}
        accent={toolColor(web)}
      />
      <Node
        pos={POS.response}
        label="RESPONSE"
        sub={tokens}
        active={a.ended}
        accent={responseAccent}
      />
    </svg>
  );
}

# NAVI-17: Web UI v1: two-pane workbench (chat + run inspector), dark cockpit default + light toggle

**Complexity: medium** | Depends on NAVI-16 (shipped: `GET /runs`, `mount_spa`) | 3 commits, one per step.

Design is DECIDED (see the two task comments): Vite + React + TypeScript + Tailwind + shadcn/ui,
static SPA built to `web/dist`, served same-origin by the existing `mount_spa` in
`src/navi/api.py` (registered after all API routes; html=True serves index at `/`). No Next.js,
no CORS, no streaming, no client router (single page). Dark "Jarvis cockpit" default theme +
light "clean workbench" toggle. v1 = chat + run inspector ONLY.

**No production Python changes in this task.** Backend is consumed as-is.

---

## 1. Directory layout

```
web/
  package.json
  vite.config.ts
  tsconfig.json / tsconfig.app.json / tsconfig.node.json   (Vite react-ts template)
  index.html                      (title "NAVI", Inter + mono font links or system stack)
  components.json                 (shadcn init)
  src/
    main.tsx
    App.tsx                       (header + two-pane grid; responsive stack on narrow screens)
    index.css                     (Tailwind v4 import, dark/light CSS-variable theme tokens,
                                   .dark custom variant, glass-panel utility, orb keyframes)
    lib/
      api.ts                      (typed fetch client -- TS mirrors of the Pydantic contracts)
      constants.ts                (APP_VERSION "0.1", ROUTE_COLORS map, BUDGET_REFERENCE_USD)
      utils.ts                    (shadcn cn helper)
    theme/
      ThemeProvider.tsx           (dark default; toggles `dark` class on <html>;
                                   persists "navi.theme" in localStorage)
    components/
      ui/                         (shadcn-generated: button, badge, card, collapsible,
                                   scroll-area, progress, input)
      Header.tsx                  (wordmark "NAVI V0.1 // ONLINE", health dot, SYS.STATUS
                                   strip, version readout, ThemeToggle)
      ThemeToggle.tsx
      Orb.tsx                     (arc-reactor orb; prop state: "idle" | "active" | "error")
      BootScreen.tsx              (empty-thread state, orb center stage)
      chat/
        ChatPane.tsx              (thread state, POST /ask flow, then GET /runs/{id})
        Message.tsx               (user/navi bubbles; navi: RouteBadge + EvidenceChip + cost)
        RouteBadge.tsx
        EvidenceChip.tsx          (collapsible source list)
        ChatInput.tsx
      inspector/
        InspectorPane.tsx         (HUD diagnostics panel; shows selected run RunTrace)
        TraceTimeline.tsx
        TraceEventRow.tsx         (per event_type rendering -- see step 2 notes)
        TotalsRow.tsx             (tokens in/out, cost vs budget meter)
```

`vite.config.ts` (the load-bearing bits):

```ts
export default defineConfig({
  plugins: [react(), tailwindcss()],   // @tailwindcss/vite (Tailwind v4)
  build: { outDir: "dist" },
  server: {
    proxy: {
      "/ask":    "http://127.0.0.1:8000",
      "/runs":   "http://127.0.0.1:8000",
      "/health": "http://127.0.0.1:8000",
    },
  },
});
```

So `npm run dev` (port 5173, HMR) works against the live API started by `start.bat`, and
`npm run build` emits `web/dist` which `mount_spa` picks up (settings default
`web_dist_dir = "web/dist"`, `src/navi/config.py:34`).

---

## 2. TS API types (`web/src/lib/api.ts`) -- transcribed from `src/navi/contracts.py`

These MUST match the Pydantic models exactly (field names are snake_case on the wire; keep them
snake_case in TS -- no remapping layer):

```ts
export type Route = "answer_inline" | "sap_review" | "research" | "clarify" | "refuse";

// POST /ask response (contracts.StructuredResult)
export interface StructuredResult {
  run_id: string;
  route: string;            // one of Route in practice; server type is plain str
  answer: string;
  evidence: string[];       // source paths / urls
  cost_usd: number;
  needs_approval: boolean;
  truncated: boolean;       // run stopped on budget -- surface as a warning chip
}

// GET /runs/{id} (contracts.RunTrace / TraceEventView)
export interface TraceEventView {
  event_type: string;       // REAL values: "route" | "model_call" | "broker_decision" | "error"
  tool_name: string | null; // broker_decision only
  route: string | null;     // "route" events only (the dispatched route)
  verdict: string | null;   // broker_decision: "allowed" | "denied" ("approval_required" reserved)
  tokens_in: number | null; // model_call only
  tokens_out: number | null;
  payload_hash: string | null; // sha256 -- NEVER clear text (see rendering notes)
  created_at: string;       // ISO-8601
}

export interface RunTrace {
  run_id: string;
  agent_id: string | null;
  route: string | null;
  status: string;
  cost_usd: number;
  started_at: string;
  ended_at: string | null;
  events: TraceEventView[];
}

// GET /runs (contracts.RunSummary) -- typed now for completeness; the v1 UI does not
// render a history page (v2), but the client exposes listRuns() so v2 needs no client change.
export interface RunSummary {
  run_id: string;
  agent_id: string | null;
  route: string | null;
  status: string;
  cost_usd: number;
  started_at: string;
  ended_at: string | null;
  tokens_in: number | null; // null = "no token data", NOT zero
  tokens_out: number | null;
}

export interface HealthResponse { status: string; db: string; }  // GET /health
```

Client approach: plain `fetch` wrappers (`ask(text)`, `getRun(runId)`, `listRuns(limit?)`,
`getHealth()`), each throwing a typed `ApiError { status, detail }` on non-2xx (FastAPI 404
body is `{"detail": "run not found"}`). No axios, no react-query -- useState/useEffect and one
`useInterval` hook for health polling. Keep the dependency surface tiny.

---

## 3. Step 1 -- scaffold + theme shell (commit 1)

`feat(web): Vite+React+Tailwind+shadcn scaffold, cockpit theme shell, orb, header (NAVI-17)`

1. Scaffold: `npm create vite@latest web -- --template react-ts` from repo root; then in
   `web/`: `npm install`, add Tailwind v4 (`tailwindcss @tailwindcss/vite`), configure the
   `@/` path alias in tsconfig `paths` + vite `resolve.alias` BEFORE shadcn, then
   `npx shadcn@latest init` (CSS variables ON, neutral base), apply the vite.config.ts
   proxy/outDir from section 1.
2. Theme tokens in `src/index.css` as CSS variables on `:root` (light) and `.dark` (default):
   - Dark cockpit: base background ~#0a0f1e (near-black navy); glass panels = translucent
     rgba fills + backdrop-blur + 1px light borders (a `.glass` utility); electric blue
     accents #2f81f7 / #38bdf8; mono font + tabular-nums for data readouts; Inter (or
     system-ui fallback) for text.
   - Light workbench: neutral grays, single blue accent, no glow.
   - Tailwind v4 dark variant: `@custom-variant dark (&:is(.dark *));`
   - Route badge palette in constants.ts (5 distinct colors): answer_inline blue,
     research violet, sap_review teal, clarify amber, refuse red.
3. `ThemeProvider.tsx`: dark by default, reads/writes `localStorage["navi.theme"]`, toggles
   the `dark` class on `document.documentElement`. `ThemeToggle.tsx` button in header.
4. `Header.tsx`: NAVI wordmark + "V0.1 // ONLINE" readout (version from
   `constants.APP_VERSION` -- /health does not return a version; add
   `// TODO(scope): expose app version via /health, then read it here`); glowing ONLINE dot
   polling `GET /health` every 10s (green ok / amber db error / red fetch failure); small
   monospace SYS.STATUS strip (e.g. `SYS.STATUS: NOMINAL | DB: OK`); theme toggle.
5. `Orb.tsx`: CSS-only arc-reactor -- nested divs for 2-3 concentric rings + core glow
   (layered box-shadows); keyframes: slow idle pulse (default), faster ring spin + brighter
   glow for state="active", red-shifted palette for state="error". No canvas, no WebGL,
   no animation library.
6. `BootScreen.tsx` + `App.tsx`: empty-state layout with the orb center stage, faint HUD
   tagline, input anchored below (placeholder in step 1). Two-pane grid shell exists but the
   right pane shows an "AWAITING RUN DATA" placeholder.
7. Build: `cd web && npm run build` -> `web/dist`; verify the existing `mount_spa`
   (`src/navi/api.py:73`) serves it at `/`.

**Acceptance criteria (step 1):**
- [ ] `cd web && npm run build` succeeds and produces `web/dist/index.html` + assets.
- [ ] `uv run pytest -q` green; ruff/mypy unaffected (zero Python files touched; the
      existing test_static_ui teardown is unaffected -- `mount_spa` already handles
      presence/absence of `web/dist` conditionally).
- [ ] `start.bat`, then http://127.0.0.1:8000/ shows the dark cockpit shell: header with
      live ONLINE dot, orb pulsing on the boot screen, theme toggle flips to light and
      persists across reload (manual check by David/orchestrator).
- [ ] `npm run dev` proxies /health to the running API (dot goes green).
- [ ] `git status` shows no `web/node_modules` or `web/dist` entries (already ignored,
      see section 5).

## 4. Step 2 -- chat + run inspector (commit 2)

`feat(web): chat thread + run inspector wired to /ask and /runs/{id} (NAVI-17)`

1. **Chat flow** (`ChatPane.tsx`): submit -> append user message -> orb state="active",
   input disabled -> `POST /ask` -> on StructuredResult: append navi message, then
   `GET /runs/{run_id}` and hand the RunTrace to the inspector (auto-select latest run).
   On HTTP/network error: in-thread error surface (red glass panel), orb state="error"
   briefly. Once the thread is non-empty the boot-screen orb shrinks into the header slot
   (conditional render + CSS transition; no shared-element animation needed).
2. **Navi message** (`Message.tsx`): answer text; RouteBadge (5-color map); EvidenceChip --
   collapsed count chip ("3 sources") expanding to the `evidence[]` list; monospace cost
   readout ($0.0123); `truncated` -> amber "BUDGET-TRUNCATED" chip; `needs_approval` ->
   amber "APPROVAL REQUIRED" chip.
3. **Run Inspector** (`InspectorPane.tsx`), HUD diagnostics styling, renders the REAL trace
   shapes (verified in `src/navi/trace.py`):
   - event_type === "route": route chip (RouteBadge color). NOTE: the wire value is
     "route", NOT "route_decision" (`trace.py:92`). Decision details exist only as a hash.
   - "model_call": MODEL CALL row with mono `tokens_in -> tokens_out`.
   - "broker_decision": tool_name + verdict glyph. Wire verdicts are exactly "allowed" /
     "denied" (`broker.py:231,265`); "approval_required" is reserved -- render amber if ever
     seen. Glyphs: allowed = green check; denied = red X. REDACTION is not a verdict --
     detect as `verdict === "allowed" && payload_hash !== null` (trace.py only sets
     payload_hash on allowed when redaction labels were folded in, `trace.py:79`) -> amber
     shield "OUTPUT REDACTED". IMPORTANT: deny reasons and redaction labels arrive as
     sha256 HASHES in payload_hash, never clear text -- render truncated mono `#a1b2c3d4...`
     with a "hashed payload" tooltip; do NOT invent reason text.
   - "error": red row; only payload_hash + created_at exist -- render ERROR + hash.
   - Timestamps: mono HH:MM:SS.mmm from created_at.
   - `TotalsRow`: sum tokens_in/tokens_out over model_call events; cost_usd vs budget meter
     (shadcn Progress). The API does NOT expose max_cost_per_run (it lives in server model
     profiles: 0.05 / 0.50 / 3.00, `src/navi/model_client.py:29-35`), so v1 uses
     `BUDGET_REFERENCE_USD = 0.50` from constants.ts, labeled "of $0.50 ref budget", with
     `// TODO(scope): expose max_cost_per_run in RunTrace and drop this constant`.
4. **Responsive**: CSS grid `lg:grid-cols-[1fr_minmax(320px,420px)]`, stacking to one column
   below lg; inspector collapses behind a "DIAGNOSTICS" toggle button on narrow screens.

**Acceptance criteria (step 2):**
- [ ] `npm run build` succeeds; `uv run pytest -q` still green; ruff/mypy unaffected
      (still zero Python changes).
- [ ] With `start.bat` running + ANTHROPIC_API_KEY set: asking a question shows orb active +
      disabled input while pending, then the answer with route badge, evidence chip
      (expand/collapse), and cost; the right pane fills with the run timeline including a
      route chip, model_call token rows, and totals; broker rows (when a tool ran) show the
      correct glyph.
- [ ] Killing the API mid-flight surfaces the in-thread error panel (no white screen);
      a 404 from /runs/{id} is handled (inspector shows "RUN NOT FOUND", thread unaffected).
- [ ] Both themes render legibly (badge colors keep contrast in light mode).

## 4b. Step 3 -- run graph canvas (commit 3) [SCOPE ADDITION, David 2026-06-12]

`feat(web): run graph view -- n8n-style workflow canvas for a run (NAVI-17)`

The n8n reference image was shown specifically for its workflow-visualization aspect: David
wants the selected run rendered as a node graph, not only a timeline. Navi's topology is FIXED
(one agent, two tools), so this is a custom fixed-layout SVG -- NO graph library (react-flow
rejected: unnecessary for ~7 static nodes; revisit only if topology becomes dynamic).

1. **Tabs** on `InspectorPane.tsx`: `TIMELINE | GRAPH` (Timeline default). Tab switch must not
   refetch or lose state (both render from the same `RunTrace` already in memory).
2. **`inspector/RunGraph.tsx`**: fixed-layout SVG (viewBox ~700x420, scales to pane width;
   no pan/zoom in v1). Static nodes: `ASK` (request) -> `ROUTER` -> `MODEL` (loop) <->
   `BROKER` -> `KB` + `WEB` tool nodes, and `RESPONSE`. Glass-panel nodes (rounded rects,
   translucent fill, 1px light border) with icon + label + mono counters; circuit-style
   edges (electric blue, subtle glow when executed). Unexecuted nodes/edges dimmed (like
   n8n's inactive nodes).
3. **Overlay from `RunTrace.events`** (REAL wire shapes -- same caveats as step 2):
   - `event_type === "route"` lights ASK->ROUTER->MODEL and labels the ROUTER edge with the
     route name (RouteBadge color).
   - Each `model_call` increments the MODEL node counter: `N calls`, summed
     `tokens_in -> tokens_out` mono readout (n8n's "N items" equivalent).
   - Each `broker_decision` lights the BROKER->tool edge for its `tool_name`:
     green=allowed (count), red glow=denied (count), amber=redacted (detected as
     `verdict === "allowed" && payload_hash !== null`, same rule as the timeline).
     Per-edge label: `3 ok / 1 denied`.
   - `error` events / run status != ok: RESPONSE node red; otherwise RESPONSE lights when
     `ended_at !== null`.
   - Hover tooltip per node: aggregates (e.g. BROKER: allowed/denied/redacted counts).
4. **Aesthetic**: same Jarvis HUD language as the rest -- glow via CSS drop-shadow/filter on
   SVG, mono labels, both themes legible (light theme: no glow, solid accent strokes).

**Acceptance criteria (step 3):**
- [ ] `npm run build` succeeds; pytest/ruff/mypy untouched (still zero Python changes).
- [ ] A run with tool calls renders: lit path, model call/token counters, per-tool edge
      counts with correct verdict colors (verify with an egress-denied run -> red WEB edge;
      a redacted run -> amber).
- [ ] Tabs switch instantly without refetch; graph scales with pane width; both themes legible.

---

## 5. .gitignore + build/deploy decision

- The root `.gitignore` ALREADY contains bare `node_modules/` (line 19) and `dist/` (line 8)
  -- both match at any depth, so `web/node_modules/` and `web/dist/` are already ignored.
  Optional clarity-only edit in step 1: a comment noting the web UI relies on those bare
  patterns (or explicit `web/dist/` / `web/node_modules/` entries). No functional change
  required. CAUTION: do not commit `web/dist` by force-adding.
- **DECISION: `web/dist` is NOT committed.** Build artifact; built locally:
  `cd web && npm install && npm run build` -- document in README run instructions (step 1
  commit).
- **start.bat: do NOT wire the npm build into startup in v1** (keeps startup fast and
  Node-optional; `mount_spa` already degrades gracefully to a UI-less API when `web/dist`
  is absent). Note in README: `# TODO(scope): wire "cd web && npm ci && npm run build" into
  start.bat (or a build.bat) once the UI stabilizes`.

## 6. Out of scope (v2+, do not build)

Microphone/voice input + ElevenLabs TTS; SAP review card rendering (Summary/Findings/Gaps/
Quick wins); runs history table page (RunSummary list is typed in api.ts but unrendered);
graph pan/zoom or a graph library (fixed SVG only -- see step 3);
streaming responses; auth; any write-action agents; SPA deep-link fallback (single page --
the existing TODO in `mount_spa` stands); exposing version/budget via API (TODOs noted above).

## 7. Risks / notes for the implementer

- Starlette route order: `mount_spa(app)` is already the last line of `api.py` -- do not
  move it; the `/` mount must stay after all API routes.
- shadcn init expects the `@/` alias; configure tsconfig paths + vite resolve.alias first.
- Keep npm dependency count minimal: react, react-dom, tailwindcss, @tailwindcss/vite,
  shadcn peer deps (class-variance-authority, clsx, tailwind-merge, lucide-react) and the
  radix primitives pulled by the 7 listed ui components. No state library, no router,
  no fetch library.
- Windows dev environment (Node v24 / npm 11 on PATH): no bash-isms in package.json scripts;
  commands run from repo root or `web/`.

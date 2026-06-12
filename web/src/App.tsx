import { BootScreen } from "@/components/BootScreen";
import { Header } from "@/components/Header";

/**
 * Two-pane workbench shell (step 1): left = conversation area (boot screen until the chat
 * lands in step 2), right = run inspector placeholder. Stacks to one column below lg.
 */
function App() {
  return (
    <div className="mx-auto flex h-dvh max-w-7xl flex-col gap-3 p-3">
      <Header />

      <main className="grid min-h-0 flex-1 gap-3 lg:grid-cols-[1fr_minmax(320px,420px)]">
        {/* Conversation pane */}
        <section className="glass flex min-h-0 flex-col rounded-lg">
          <div className="min-h-0 flex-1 overflow-y-auto">
            <BootScreen />
          </div>
          {/* Step 2 replaces this with ChatInput wired to POST /ask. */}
          <div className="border-t border-border p-3">
            <input
              type="text"
              disabled
              placeholder="Ask anything… (chat lands in the next step)"
              className="readout w-full rounded-md border border-input bg-transparent px-3 py-2.5 text-sm text-foreground placeholder:text-muted-foreground/60 focus:outline-none"
            />
          </div>
        </section>

        {/* Run inspector pane (placeholder until step 2) */}
        <aside className="glass hidden min-h-0 flex-col rounded-lg p-4 lg:flex">
          <h2 className="readout text-[10px] uppercase tracking-[0.3em] text-muted-foreground">
            Run Inspector
          </h2>
          <div className="flex flex-1 items-center justify-center">
            <p className="readout text-xs text-muted-foreground/60">AWAITING RUN DATA</p>
          </div>
        </aside>
      </main>
    </div>
  );
}

export default App;

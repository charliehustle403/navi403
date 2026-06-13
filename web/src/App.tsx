import { useEffect, useRef, useState } from "react";

import { BootScreen } from "@/components/BootScreen";
import { Header } from "@/components/Header";
import { ChatInput } from "@/components/chat/ChatInput";
import { Message, type ChatMessage } from "@/components/chat/Message";
import { InspectorPane } from "@/components/inspector/InspectorPane";
import { ApiError, ask, getRun, type RunTrace } from "@/lib/api";

/**
 * Two-pane workbench: left = conversation (boot screen until the first ask),
 * right = run inspector showing the latest run's trace. Stacks below lg with a
 * DIAGNOSTICS toggle for the inspector.
 */
function App() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [pending, setPending] = useState(false);
  const [trace, setTrace] = useState<RunTrace | null>(null);
  const [traceError, setTraceError] = useState<string | null>(null);
  const [showInspector, setShowInspector] = useState(false);
  const nextId = useRef(0);
  const threadEnd = useRef<HTMLDivElement>(null);

  useEffect(() => {
    threadEnd.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, pending]);

  const submit = async (text: string) => {
    setMessages((m) => [...m, { id: nextId.current++, role: "user", text }]);
    setPending(true);
    try {
      const result = await ask(text);
      setMessages((m) => [
        ...m,
        { id: nextId.current++, role: "navi", text: result.answer, result },
      ]);
      try {
        setTrace(await getRun(result.run_id));
        setTraceError(null);
      } catch (e) {
        setTrace(null);
        setTraceError(e instanceof ApiError && e.status === 404 ? "RUN NOT FOUND" : "TRACE UNAVAILABLE");
      }
    } catch (e) {
      const detail =
        e instanceof ApiError ? e.detail : "API unreachable — is the server running? (start.bat)";
      setMessages((m) => [...m, { id: nextId.current++, role: "navi", text: "", error: detail }]);
    } finally {
      setPending(false);
    }
  };

  const started = messages.length > 0;
  const orbState = pending ? "active" : "idle";

  return (
    <div className="mx-auto flex h-dvh max-w-7xl flex-col gap-3 p-3">
      <Header showOrb={started} orbActive={pending} />

      <main className="grid min-h-0 flex-1 gap-3 lg:grid-cols-[1fr_minmax(320px,420px)]">
        {/* Conversation pane */}
        <section className="glass flex min-h-0 flex-col rounded-lg">
          <div className="min-h-0 flex-1 overflow-y-auto">
            {started ? (
              <div className="space-y-3 p-4">
                {messages.map((msg) => (
                  <Message key={msg.id} message={msg} />
                ))}
                {pending && (
                  <p className="readout animate-pulse text-[10px] uppercase tracking-[0.25em] text-muted-foreground">
                    processing…
                  </p>
                )}
                <div ref={threadEnd} />
              </div>
            ) : (
              <BootScreen orbState={orbState} />
            )}
          </div>
          <ChatInput disabled={pending} onSubmit={(text) => void submit(text)} />
        </section>

        {/* Run inspector — always visible at lg+, toggled below */}
        <aside
          className={`glass min-h-0 flex-col rounded-lg lg:flex ${showInspector ? "flex" : "hidden"}`}
        >
          <InspectorPane trace={trace} error={traceError} />
        </aside>
      </main>

      {/* Narrow-screen diagnostics toggle */}
      <button
        type="button"
        onClick={() => setShowInspector((s) => !s)}
        className="readout glass rounded-md px-3 py-1.5 text-[10px] uppercase tracking-[0.25em] text-muted-foreground lg:hidden"
      >
        {showInspector ? "▾ Hide diagnostics" : "▸ Diagnostics"}
      </button>
    </div>
  );
}

export default App;

import { Orb, type OrbState } from "@/components/Orb";

/**
 * Empty-thread state: the arc-reactor orb center stage with a faint HUD tagline,
 * JARVIS-boot-screen style. Replaced by the conversation thread after the first ask.
 */
export function BootScreen({ orbState = "idle" }: { orbState?: OrbState }) {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-8 py-16">
      <Orb state={orbState} size={220} />
      <div className="text-center">
        <p className="readout text-xs uppercase tracking-[0.35em] text-muted-foreground">
          Technical Workbench
        </p>
        <p className="mt-2 text-sm text-muted-foreground/70">
          Ask a question, run grounded research, or paste an SAP role design for review.
        </p>
      </div>
    </div>
  );
}

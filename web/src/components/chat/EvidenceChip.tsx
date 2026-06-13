import { useState } from "react";

/** Collapsed "N sources" chip expanding to the cited evidence list. */
export function EvidenceChip({ evidence }: { evidence: string[] }) {
  const [open, setOpen] = useState(false);
  if (evidence.length === 0) return null;

  return (
    <div>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="readout rounded border border-border px-1.5 py-0.5 text-[9px] uppercase tracking-[0.15em] text-muted-foreground transition-colors hover:text-foreground"
        aria-expanded={open}
      >
        {open ? "▾" : "▸"} {evidence.length} {evidence.length === 1 ? "source" : "sources"}
      </button>
      {open && (
        <ul className="mt-1.5 space-y-1 border-l border-border pl-2.5">
          {evidence.map((src) => (
            <li key={src} className="readout break-all text-[10px] text-muted-foreground">
              {src}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

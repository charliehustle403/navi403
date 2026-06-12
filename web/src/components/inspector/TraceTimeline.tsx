import { TraceEventRow } from "@/components/inspector/TraceEventRow";
import type { TraceEventView } from "@/lib/api";

export function TraceTimeline({ events }: { events: TraceEventView[] }) {
  if (events.length === 0) {
    return <p className="readout py-4 text-center text-xs text-muted-foreground/60">NO EVENTS</p>;
  }
  return (
    <ul className="divide-y divide-border/50">
      {events.map((event, i) => (
        <TraceEventRow key={`${event.created_at}-${i}`} event={event} />
      ))}
    </ul>
  );
}

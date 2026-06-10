import type { ActivityRow } from "../types";

interface Props {
  rows: ActivityRow[];
}

const KIND_CLASS: Record<string, string> = {
  trade_open: "pos",
  trade_close: "pos",
  forecast: "",
  escalation: "",
  resolve: "",
  resolve_void: "dim",
  trade_skip: "dim",
  triage_reject: "dim",
  analyst_reject: "dim",
  error: "neg",
};

function fmtTime(iso: string): string {
  const d = new Date(`${iso}Z`);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

export default function ActivityFeed({ rows }: Props): JSX.Element {
  return (
    <section className="card">
      <h2 className="card-title">Activity — what the system is doing and why</h2>
      <ul className="events activity-list">
        {rows.length === 0 && <li className="empty">No activity yet.</li>}
        {rows.map((r) => (
          <li key={r.id} className="event" title={r.message}>
            <span className="event-time">{fmtTime(r.ts)}</span>
            <span className={`source-tag ${KIND_CLASS[r.kind] ?? ""}`}>
              {r.kind.replace("_", " ")}
            </span>
            <span className="event-title activity-msg">{r.message}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}

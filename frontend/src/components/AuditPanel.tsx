import type { AuditRow } from "../types";

interface Props {
  rows: AuditRow[];
}

export default function AuditPanel({ rows }: Props): JSX.Element {
  return (
    <section className="card">
      <h2 className="card-title">Ledger audit — invariants</h2>
      <ul className="events">
        {rows.length === 0 && <li className="empty">Audit not yet run.</li>}
        {rows.map((r) => (
          <li key={r.check} className="event" title={r.detail}>
            <span className={`dot ${r.ok ? "dot-on" : "dot-bad"}`} />
            <span className="event-title">
              <strong>{r.check}</strong>{" "}
              <span className={r.ok ? "dim" : "neg"}>{r.detail}</span>
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}

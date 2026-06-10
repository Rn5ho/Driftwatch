import type { EventItem } from "../types";

interface Props {
  events: EventItem[];
}

function relTime(ts: string | null): string {
  if (!ts) return "—";
  const d = new Date(/[zZ]|[+-]\d{2}:?\d{2}$/.test(ts) ? ts : `${ts}Z`);
  if (Number.isNaN(d.getTime())) return "—";
  const seconds = Math.max(0, Math.floor((Date.now() - d.getTime()) / 1000));
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

export default function EventsFeed({ events }: Props): JSX.Element {
  return (
    <section className="card">
      <h2 className="card-title">Events</h2>
      <ul className="events">
        {events.length === 0 && <li className="empty">No events yet.</li>}
        {events.map((e) => (
          <li key={e.id} className="event">
            <span className="source-tag">{e.source}</span>
            <span className="event-title">
              {e.url ? (
                <a href={e.url} target="_blank" rel="noopener noreferrer">
                  {e.title}
                </a>
              ) : (
                e.title
              )}
            </span>
            <span className="event-time">
              {relTime(e.published_at ?? e.fetched_at)}
            </span>
            <span
              className={`dot ${e.processed ? "dot-on" : "dot-off"}`}
              title={e.processed ? "processed" : "pending"}
            />
          </li>
        ))}
      </ul>
    </section>
  );
}

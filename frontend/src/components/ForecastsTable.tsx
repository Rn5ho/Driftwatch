import type { Forecast } from "../types";

interface Props {
  forecasts: Forecast[];
}

function fmtTime(ts: string | null): string {
  if (!ts) return "—";
  const d = new Date(/[zZ]|[+-]\d{2}:?\d{2}$/.test(ts) ? ts : `${ts}Z`);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toISOString().slice(5, 16).replace("T", " ");
}

function directionClass(direction: string): string {
  if (direction === "long") return "badge badge-long";
  if (direction === "short") return "badge badge-short";
  return "badge badge-none";
}

function outcomeMark(outcome: number | null): string {
  if (outcome === 1) return "✓";
  if (outcome === 0) return "✗";
  return "—";
}

export default function ForecastsTable({ forecasts }: Props): JSX.Element {
  return (
    <section className="card">
      <h2 className="card-title">Forecasts</h2>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Time</th>
              <th>Asset</th>
              <th>Dir</th>
              <th>P</th>
              <th>Category</th>
              <th>Horizon</th>
              <th>Outcome</th>
              <th>Brier</th>
            </tr>
          </thead>
          <tbody>
            {forecasts.length === 0 && (
              <tr>
                <td colSpan={8} className="empty">
                  No forecasts yet.
                </td>
              </tr>
            )}
            {forecasts.map((f) => (
              <tr key={f.id} title={f.thesis}>
                <td className="num">{fmtTime(f.created_at)}</td>
                <td>{f.asset}</td>
                <td>
                  <span className={directionClass(f.direction)}>
                    {f.direction}
                  </span>
                </td>
                <td className="num">{Math.round(f.probability * 100)}%</td>
                <td>{f.category}</td>
                <td className="num">{f.horizon_hours}h</td>
                <td
                  className={
                    f.outcome === 1 ? "pos" : f.outcome === 0 ? "neg" : "dim"
                  }
                >
                  {outcomeMark(f.outcome)}
                </td>
                <td className="num">
                  {f.brier === null ? "—" : f.brier.toFixed(3)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

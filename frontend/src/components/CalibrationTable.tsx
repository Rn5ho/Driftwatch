import type { CalibrationRow } from "../types";

interface Props {
  rows: CalibrationRow[];
}

function fmtPct(v: number | null): string {
  if (v === null || !Number.isFinite(v)) return "—";
  return `${Math.round(v * 100)}%`;
}

function fmtBrier(v: number | null): string {
  if (v === null || !Number.isFinite(v)) return "—";
  return v.toFixed(3);
}

export default function CalibrationTable({ rows }: Props): JSX.Element {
  return (
    <section className="card">
      <h2 className="card-title">Calibration</h2>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Category</th>
              <th>N</th>
              <th>Mean Brier</th>
              <th>Hit rate</th>
              <th>Mean P</th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 && (
              <tr>
                <td colSpan={5} className="empty">
                  No resolved forecasts yet.
                </td>
              </tr>
            )}
            {rows.map((r) => (
              <tr key={r.category}>
                <td>{r.category}</td>
                <td className="num">{r.n}</td>
                <td className="num">{fmtBrier(r.mean_brier)}</td>
                <td className="num">{fmtPct(r.hit_rate)}</td>
                <td className="num">{fmtPct(r.mean_probability)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

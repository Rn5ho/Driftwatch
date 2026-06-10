import type { ModelRow } from "../types";

interface Props {
  rows: ModelRow[];
}

function fmtPct(v: number | null): string {
  if (v === null || !Number.isFinite(v)) return "—";
  return `${Math.round(v * 100)}%`;
}

function fmtBrier(v: number | null): string {
  if (v === null || !Number.isFinite(v)) return "—";
  return v.toFixed(3);
}

/** Shorten model ids for display: "claude-sonnet-4-6" → "sonnet-4-6". */
function fmtModel(model: string): string {
  return model.replace(/^claude-/, "");
}

export default function ModelsTable({ rows }: Props): JSX.Element {
  return (
    <section className="card">
      <h2 className="card-title">Model comparison</h2>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Model</th>
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
                  No resolved forecasts yet — shadow pairs accrue automatically.
                </td>
              </tr>
            )}
            {rows.map((r) => (
              <tr key={r.model}>
                <td>{fmtModel(r.model)}</td>
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

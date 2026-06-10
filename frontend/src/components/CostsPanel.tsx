import type { CostsSummary } from "../types";

interface Props {
  costs: CostsSummary | null;
}

function fmtModel(model: string): string {
  return model.replace(/^claude-/, "");
}

export default function CostsPanel({ costs }: Props): JSX.Element {
  const byModel = costs?.by_model ?? [];
  const byRole = costs?.by_role ?? [];
  return (
    <section className="card">
      <h2 className="card-title">LLM spend</h2>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Model</th>
              <th>Calls</th>
              <th>In tok</th>
              <th>Out tok</th>
              <th>Cost</th>
            </tr>
          </thead>
          <tbody>
            {byModel.length === 0 && (
              <tr>
                <td colSpan={5} className="empty">
                  No LLM calls recorded yet.
                </td>
              </tr>
            )}
            {byModel.map((r) => (
              <tr key={r.model}>
                <td>{fmtModel(r.model)}</td>
                <td className="num">{r.calls}</td>
                <td className="num">{r.input_tokens.toLocaleString()}</td>
                <td className="num">{r.output_tokens.toLocaleString()}</td>
                <td className="num">${r.cost_usd.toFixed(4)}</td>
              </tr>
            ))}
            {byRole.map((r) => (
              <tr key={`role-${r.role}`}>
                <td className="dim">↳ {r.role}</td>
                <td className="num dim">{r.calls}</td>
                <td className="num dim" colSpan={2}></td>
                <td className="num dim">${r.cost_usd.toFixed(4)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

import type { Trade } from "../types";

interface Props {
  trades: Trade[];
}

function fmtTime(ts: string | null): string {
  if (!ts) return "—";
  const d = new Date(/[zZ]|[+-]\d{2}:?\d{2}$/.test(ts) ? ts : `${ts}Z`);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toISOString().slice(5, 16).replace("T", " ");
}

function fmtNum(v: number | null, digits = 2): string {
  if (v === null || !Number.isFinite(v)) return "—";
  return v.toLocaleString("en-US", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

function sideClass(side: string): string {
  if (side === "long") return "badge badge-long";
  if (side === "short") return "badge badge-short";
  return "badge badge-none";
}

function pnlClass(pnl: number | null): string {
  if (pnl === null || pnl === 0) return "num";
  return pnl > 0 ? "num pos" : "num neg";
}

export default function TradesTable({ trades }: Props): JSX.Element {
  return (
    <section className="card">
      <h2 className="card-title">Trades</h2>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Time</th>
              <th>Asset</th>
              <th>Side</th>
              <th>Notional</th>
              <th>Entry</th>
              <th>Exit</th>
              <th>PnL</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {trades.length === 0 && (
              <tr>
                <td colSpan={8} className="empty">
                  No trades yet.
                </td>
              </tr>
            )}
            {trades.map((t) => (
              <tr key={t.id}>
                <td className="num">{fmtTime(t.entry_ts)}</td>
                <td>{t.asset}</td>
                <td>
                  <span className={sideClass(t.side)}>{t.side}</span>
                </td>
                <td className="num">{fmtNum(t.notional)}</td>
                <td className="num">{fmtNum(t.entry_price)}</td>
                <td className="num">{fmtNum(t.exit_price)}</td>
                <td className={pnlClass(t.pnl)}>{fmtNum(t.pnl)}</td>
                <td className={t.status === "open" ? "dim" : ""}>{t.status}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

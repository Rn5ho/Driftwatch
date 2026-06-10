import type { PortfolioSummary, Trade } from "../types";

interface Props {
  portfolio: PortfolioSummary | null;
  trades: Trade[];
}

function fmtMoney(v: number | null | undefined): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return "—";
  return v.toLocaleString("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

function pnlClass(v: number | null | undefined): string {
  if (v === null || v === undefined || v === 0) return "num";
  return v > 0 ? "num pos" : "num neg";
}

export default function PortfolioBar({ portfolio, trades }: Props): JSX.Element {
  // Fallbacks computed from the (limited) trades list when the route does not
  // enrich the portfolio row. Cash only changes at trade close, so realized
  // PnL = cash − starting_cash holds exactly.
  const openCount =
    portfolio?.open_trades ?? trades.filter((t) => t.status === "open").length;
  const closedCount =
    portfolio?.closed_trades ??
    trades.filter((t) => t.status === "closed").length;
  const fees =
    portfolio?.total_fees ?? trades.reduce((acc, t) => acc + (t.fees ?? 0), 0);
  const realized =
    portfolio?.realized_pnl ??
    (portfolio ? portfolio.cash - portfolio.starting_cash : null);
  const equity = portfolio?.equity ?? portfolio?.cash ?? null;

  return (
    <section className="card portfolio-bar">
      <h2 className="card-title">Portfolio</h2>
      <div className="stats">
        <div className="stat">
          <span className="stat-label">Equity</span>
          <span className="num stat-value">{fmtMoney(equity)}</span>
        </div>
        <div className="stat">
          <span className="stat-label">Cash</span>
          <span className="num stat-value">{fmtMoney(portfolio?.cash)}</span>
        </div>
        <div className="stat">
          <span className="stat-label">Realized PnL</span>
          <span className={`stat-value ${pnlClass(realized)}`}>
            {fmtMoney(realized)}
          </span>
        </div>
        <div className="stat">
          <span className="stat-label">Open / Closed</span>
          <span className="num stat-value">
            {openCount} / {closedCount}
          </span>
        </div>
        <div className="stat">
          <span className="stat-label">Fees</span>
          <span className="num stat-value">{fmtMoney(fees)}</span>
        </div>
      </div>
    </section>
  );
}

import type { AuditRow, OpsStatus } from "../types";

interface Props {
  status: OpsStatus | null;
  audit: AuditRow[];
}

function fmtPct(v: number | null | undefined): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return "—";
  return `${Math.round(v * 100)}%`;
}

function fmtUsd(v: number | null | undefined): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return "—";
  return `$${v.toFixed(2)}`;
}

function ago(iso: string | null | undefined): string {
  if (!iso) return "—";
  const ms = Date.now() - new Date(`${iso}Z`).getTime();
  if (!Number.isFinite(ms) || ms < 0) return "—";
  const min = Math.floor(ms / 60_000);
  if (min < 1) return "now";
  if (min < 60) return `${min}m ago`;
  return `${Math.floor(min / 60)}h ago`;
}

export default function OpsBar({ status, audit }: Props): JSX.Element {
  const auditBad = audit.filter((a) => !a.ok).length;
  const auditState =
    audit.length === 0 ? "—" : auditBad === 0 ? "all clear" : `${auditBad} FAILING`;
  const stages = status?.forecasts_by_stage ?? {};
  const stageSummary = Object.entries(stages)
    .map(([k, v]) => `${v} ${k}`)
    .join(" · ");

  return (
    <section className="card portfolio-bar">
      <h2 className="card-title">System</h2>
      <div className="stats">
        <div className="stat">
          <span className="stat-label">Queue</span>
          <span className="num stat-value">{status?.unprocessed_events ?? "—"}</span>
        </div>
        <div className="stat">
          <span className="stat-label">Events 24h</span>
          <span className="num stat-value">{status?.events_24h ?? "—"}</span>
        </div>
        <div className="stat">
          <span className="stat-label">Triage pass</span>
          <span className="num stat-value">{fmtPct(status?.triage_pass_rate)}</span>
        </div>
        <div className="stat">
          <span className="stat-label">Forecasts</span>
          <span className="num stat-value">{stageSummary || "—"}</span>
        </div>
        <div className="stat">
          <span className="stat-label">Cost 24h / total</span>
          <span className="num stat-value">
            {fmtUsd(status?.cost_24h_usd)} / {fmtUsd(status?.cost_total_usd)}
          </span>
        </div>
        <div className="stat">
          <span className="stat-label">Last event / snapshot</span>
          <span className="num stat-value">
            {ago(status?.last_event_at)} / {ago(status?.last_snapshot_at)}
          </span>
        </div>
        <div className="stat">
          <span className="stat-label">Audit</span>
          <span className={`stat-value ${auditBad > 0 ? "neg" : "pos"}`}>{auditState}</span>
        </div>
      </div>
    </section>
  );
}

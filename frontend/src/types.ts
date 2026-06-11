/**
 * Types mirroring the backend ORM rows (app/models.py) as serialized by
 * FastAPI: datetimes become ISO strings (naive UTC), nullable columns become
 * `T | null`.
 */

export interface EventItem {
  id: number;
  source: string;
  category: string;
  title: string;
  /** Not included in the GET /api/events payload (route returns a trimmed projection). */
  summary?: string;
  url: string;
  published_at: string | null;
  fetched_at: string;
  /** Not included in the GET /api/events payload (route returns a trimmed projection). */
  content_hash?: string;
  processed: boolean;
}

export interface Forecast {
  id: number;
  event_id: number | null;
  asset: string; // "BTC" | "ETH" | "SOL" | "NONE"
  category: string;
  direction: string; // "long" | "short" | "none"
  probability: number;
  market_prior: number | null;
  horizon_hours: number;
  thesis: string;
  what_is_priced_in: string;
  key_risks: string;
  model: string;
  /** "analysis" | "escalation" | "shadow" — which cascade stage produced this. */
  stage?: string;
  /** Shadow forecasts are model-comparison data, never traded. */
  shadow?: boolean;
  /** Market regime at creation, e.g. "up/high_vol"; "" when unknown. */
  regime?: string;
  created_at: string;
  price_at_forecast: number | null;
  resolved_at: string | null;
  price_at_resolution: number | null;
  outcome: number | null; // 1 thesis true, 0 false
  brier: number | null;
}

export interface Trade {
  id: number;
  forecast_id: number;
  asset: string;
  side: string; // "long" | "short"
  notional: number;
  entry_price: number;
  entry_ts: string;
  exit_price: number | null;
  exit_ts: string | null;
  fees: number;
  pnl: number | null;
  status: string; // "open" | "closed"
  closes_at: string | null; // scheduled close (open trades only)
}

/**
 * GET /api/portfolio. The Portfolio ORM row guarantees cash/starting_cash;
 * the route may enrich with derived fields, so those are optional and the
 * dashboard computes fallbacks from the trades list when absent.
 */
export interface PortfolioSummary {
  cash: number;
  starting_cash: number;
  equity?: number | null;
  realized_pnl?: number | null;
  open_trades?: number | null;
  closed_trades?: number | null;
  total_fees?: number | null;
  created_at?: string | null;
  updated_at?: string | null;
}

/** GET /api/calibration — shape fixed by the SPEC §6 calibration_report contract. */
export interface CalibrationRow {
  category: string;
  n: number;
  mean_brier: number | null;
  hit_rate: number | null;
  mean_probability: number | null;
}

/** GET /api/models — per-model Brier comparison (shadow forecasts included). */
export interface ModelRow {
  model: string;
  n: number;
  mean_brier: number | null;
  hit_rate: number | null;
  mean_probability: number | null;
}

/** GET /api/ops/activity — the system narrating its decisions. */
export interface ActivityRow {
  id: number;
  ts: string;
  kind: string;
  message: string;
  event_id: number | null;
  forecast_id: number | null;
  trade_id: number | null;
}

/** GET /api/ops/status. */
export interface OpsStatus {
  unprocessed_events: number;
  events_24h: number;
  triage_pass_rate: number | null;
  forecasts_by_stage: Record<string, number>;
  cost_total_usd: number;
  cost_24h_usd: number;
  last_event_at: string | null;
  last_snapshot_at: string | null;
  last_activity_at: string | null;
  open_trades: number;
}

/** GET /api/ops/costs. */
export interface CostModelRow {
  model: string;
  calls: number;
  input_tokens: number;
  output_tokens: number;
  cost_usd: number;
}

export interface CostRoleRow {
  role: string;
  calls: number;
  cost_usd: number;
}

export interface CostsSummary {
  by_model: CostModelRow[];
  by_role: CostRoleRow[];
}

/** GET /api/ops/audit — ledger invariants; every row should be ok. */
export interface AuditRow {
  check: string;
  ok: boolean;
  detail: string;
}

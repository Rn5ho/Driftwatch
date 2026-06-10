import type {
  ActivityRow,
  AuditRow,
  CalibrationRow,
  CostsSummary,
  EventItem,
  Forecast,
  ModelRow,
  OpsStatus,
  PortfolioSummary,
  Trade,
} from "./types";

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(path, { headers: { Accept: "application/json" } });
  if (!res.ok) {
    throw new Error(`GET ${path} failed: ${res.status}`);
  }
  return (await res.json()) as T;
}

async function postJson<T>(path: string): Promise<T> {
  const res = await fetch(path, {
    method: "POST",
    headers: { Accept: "application/json" },
  });
  if (!res.ok) {
    throw new Error(`POST ${path} failed: ${res.status}`);
  }
  return (await res.json()) as T;
}

export function fetchPortfolio(): Promise<PortfolioSummary> {
  return getJson<PortfolioSummary>("/api/portfolio");
}

export function fetchForecasts(limit = 50): Promise<Forecast[]> {
  return getJson<Forecast[]>(`/api/forecasts?limit=${limit}`);
}

export function fetchTrades(limit = 50): Promise<Trade[]> {
  return getJson<Trade[]>(`/api/trades?limit=${limit}`);
}

export function fetchEvents(limit = 50): Promise<EventItem[]> {
  return getJson<EventItem[]>(`/api/events?limit=${limit}`);
}

export function fetchCalibration(): Promise<CalibrationRow[]> {
  return getJson<CalibrationRow[]>("/api/calibration");
}

export function fetchModels(): Promise<ModelRow[]> {
  return getJson<ModelRow[]>("/api/models");
}

export function fetchOpsStatus(): Promise<OpsStatus> {
  return getJson<OpsStatus>("/api/ops/status");
}

export function fetchActivity(limit = 100): Promise<ActivityRow[]> {
  return getJson<ActivityRow[]>(`/api/ops/activity?limit=${limit}`);
}

export function fetchCosts(): Promise<CostsSummary> {
  return getJson<CostsSummary>("/api/ops/costs");
}

export function fetchAudit(): Promise<AuditRow[]> {
  return getJson<AuditRow[]>("/api/ops/audit");
}

export function runIngest(): Promise<unknown> {
  return postJson<unknown>("/api/run/ingest");
}

export function runAnalyze(): Promise<unknown> {
  return postJson<unknown>("/api/run/analyze");
}

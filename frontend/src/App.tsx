import { useCallback, useEffect, useState } from "react";

import {
  fetchActivity,
  fetchAudit,
  fetchCalibration,
  fetchCosts,
  fetchEvents,
  fetchForecasts,
  fetchModels,
  fetchOpsStatus,
  fetchPortfolio,
  fetchTrades,
  runAnalyze,
  runIngest,
} from "./api";
import ActivityFeed from "./components/ActivityFeed";
import AuditPanel from "./components/AuditPanel";
import CalibrationTable from "./components/CalibrationTable";
import CostsPanel from "./components/CostsPanel";
import EventsFeed from "./components/EventsFeed";
import ForecastsTable from "./components/ForecastsTable";
import ModelsTable from "./components/ModelsTable";
import OpsBar from "./components/OpsBar";
import PortfolioBar from "./components/PortfolioBar";
import TradesTable from "./components/TradesTable";
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

const POLL_MS = 30_000;

type RunAction = "ingest" | "analyze";

export default function App(): JSX.Element {
  const [portfolio, setPortfolio] = useState<PortfolioSummary | null>(null);
  const [forecasts, setForecasts] = useState<Forecast[]>([]);
  const [trades, setTrades] = useState<Trade[]>([]);
  const [events, setEvents] = useState<EventItem[]>([]);
  const [calibration, setCalibration] = useState<CalibrationRow[]>([]);
  const [models, setModels] = useState<ModelRow[]>([]);
  const [activity, setActivity] = useState<ActivityRow[]>([]);
  const [opsStatus, setOpsStatus] = useState<OpsStatus | null>(null);
  const [costs, setCosts] = useState<CostsSummary | null>(null);
  const [audit, setAudit] = useState<AuditRow[]>([]);
  const [offline, setOffline] = useState(false);
  const [busy, setBusy] = useState<RunAction | null>(null);

  const refresh = useCallback(async (): Promise<void> => {
    const [p, f, t, e, c, m, a, s, co, au] = await Promise.allSettled([
      fetchPortfolio(),
      fetchForecasts(50),
      fetchTrades(50),
      fetchEvents(50),
      fetchCalibration(),
      fetchModels(),
      fetchActivity(100),
      fetchOpsStatus(),
      fetchCosts(),
      fetchAudit(),
    ]);

    let failed = false;
    if (p.status === "fulfilled") setPortfolio(p.value);
    else failed = true;
    if (f.status === "fulfilled") setForecasts(f.value);
    else failed = true;
    if (t.status === "fulfilled") setTrades(t.value);
    else failed = true;
    if (e.status === "fulfilled") setEvents(e.value);
    else failed = true;
    if (c.status === "fulfilled") setCalibration(c.value);
    else failed = true;
    if (m.status === "fulfilled") setModels(m.value);
    else failed = true;
    if (a.status === "fulfilled") setActivity(a.value);
    else failed = true;
    if (s.status === "fulfilled") setOpsStatus(s.value);
    else failed = true;
    if (co.status === "fulfilled") setCosts(co.value);
    else failed = true;
    if (au.status === "fulfilled") setAudit(au.value);
    else failed = true;

    setOffline(failed);
  }, []);

  useEffect(() => {
    void refresh();
    const id = window.setInterval(() => {
      void refresh();
    }, POLL_MS);
    return () => window.clearInterval(id);
  }, [refresh]);

  const handleRun = useCallback(
    async (action: RunAction): Promise<void> => {
      setBusy(action);
      try {
        await (action === "ingest" ? runIngest() : runAnalyze());
      } catch {
        setOffline(true);
      } finally {
        setBusy(null);
        void refresh();
      }
    },
    [refresh],
  );

  return (
    <div className="app">
      {offline && (
        <div className="banner" role="alert">
          Could not reach the API — backend offline?
        </div>
      )}

      <header className="header">
        <h1>
          DriftWatch <span className="header-sub">paper-trading ledger</span>
        </h1>
        <div className="header-actions">
          <button
            type="button"
            disabled={busy !== null}
            onClick={() => void handleRun("ingest")}
          >
            {busy === "ingest" ? "Running…" : "Run ingest"}
          </button>
          <button
            type="button"
            disabled={busy !== null}
            onClick={() => void handleRun("analyze")}
          >
            {busy === "analyze" ? "Running…" : "Run analyze"}
          </button>
        </div>
      </header>

      <PortfolioBar portfolio={portfolio} trades={trades} />
      <OpsBar status={opsStatus} audit={audit} />

      <div className="grid">
        <div className="col">
          <ActivityFeed rows={activity} />
          <ForecastsTable forecasts={forecasts} />
          <TradesTable trades={trades} />
        </div>
        <div className="col">
          <EventsFeed events={events} />
          <CalibrationTable rows={calibration} />
          <ModelsTable rows={models} />
          <CostsPanel costs={costs} />
          <AuditPanel rows={audit} />
        </div>
      </div>
    </div>
  );
}

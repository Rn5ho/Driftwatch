# DriftWatch — Specification v0.1

*A news-driven crypto paper-trading system that competes on reading, patience, and calibration — never on speed.*

Date: 2026-06-10. Status: MVP scaffold.

---

## 1. Philosophy

The "default project" (poll news → ask LLM bullish/bearish → market order → contaminated backtest → abandoned in 3 months) fails for five documented reasons. DriftWatch is designed as the point-by-point negation of each:

| # | Why the default project fails | DriftWatch design answer |
|---|---|---|
| 1 | Backtest is unfalsifiable (LLM memorized history) | **Forward-only.** No backtests. Every forecast is logged *before* the outcome with honest timestamps. The dataset we build IS the product. |
| 2 | News is priced in within seconds; retail latency loses | **Trade the drift, not the jump.** Minimum horizon hours-to-days. Hard no-trade window (15 min) after macro prints. We log `published_at` vs `fetched_at` latency on every event. |
| 3 | Fees and overtrading erase paper alpha | **Cost model on every paper fill** (configurable round-trip bps covering fee + spread + slippage). High conviction threshold; few trades. |
| 4 | Raw sentiment ignores what's already expected | **Expectation-gap scoring.** The analyst must state `what_is_priced_in` and we record a market-implied prior (Polymarket odds where applicable). Edge = our probability − prior. |
| 5 | LLMs fail at risk management, not reading (Alpha Arena: 4/6 frontier models blew up on leverage) | **LLM forecasts probabilities only. Sizing is deterministic code**: fractional Kelly, hard caps, funding-rate veto. The model never chooses size. |

### Edge hypotheses (research-verified 2026-06-10)

| Edge | Verdict | Role in system |
|---|---|---|
| Calibration/superforecasting loop (Brier per category, size by calibrated conviction) | STRONG (infrastructure) | **The chassis.** Self-learning loop. |
| Positioning confluence (news + funding/OI extremes → post-flush reversion) | STRONG | **Veto + sizing layer** (MVP: funding veto; later: flush detection). |
| Slow news (token unlocks, SEC filings, governance diffs) | STRONG (unlocks proven: ~90% of 16k unlocks negative, multi-day window) | **Alpha engine.** MVP: EDGAR crypto filings feed. Phase 1: unlock calendar. |
| Expectation-gap on macro prints | STRONG concept, weak at minute-speed | Trade post-print drift only (30min–48h), never the jump. |
| Per-category reaction profiles (overreaction fade) | PROMISING, unvalidated | **Data-collection mode** — the forecast ledger builds this dataset free. |
| Prediction-market divergence | WEAK as signal | Demoted to **instrumentation**: Polymarket odds = priced-in prior. |

Key supporting literature: Lopez-Lira & Tang (drift survives ≤10bps, dies at 20bps); FINSABER (in-window LLM backtests are artifacts); Keyrock 16k-unlock study; "Lazy Prices" (Cohen & Malloy — filing *changes* earn 188bps/mo from inattention); AIA Forecaster (Platt-scaled LLMs reach superforecaster Brier parity); crypto carry/liquidation literature (SSRN 4666425).

---

## 2. Architecture

```
driftwatch/
  SPEC.md                  ← this file
  README.md
  backend/
    requirements.txt
    .env.example
    app/
      config.py            # Settings (pydantic-settings, DRIFTWATCH_* env)
      db.py                # async SQLAlchemy engine/session, Base, init_db, session_scope
      models.py            # ORM: Event, MarketSnapshot, OddsSnapshot, Forecast, Trade, Portfolio
      schemas.py           # ForecastOutput (LLM structured output contract)
      pipeline.py          # orchestration: events → analyst → forecast → (filters) → trade
      scheduler.py         # APScheduler jobs
      main.py              # FastAPI app, CORS, lifespan (init_db + scheduler)
      ingest/
        base.py            # content_hash, store_events (dedupe)
        rss.py             # 5 RSS feeds incl. trumpstruth.org
        prices.py          # Binance spot prices, snapshot_markets
        derivs.py          # Binance futures funding + open interest
        polymarket.py      # Gamma API odds (priced-in priors)
        edgar.py           # SEC full-text search (crypto 8-Ks etc.)
      analysis/
        prompts.py         # FROZEN system prompt (cacheable — no timestamps ever)
        analyst.py         # Claude structured-output call → ForecastOutput
        calibration.py     # Brier scores per category
      trading/
        sizing.py          # fractional Kelly, caps, funding veto
        paper.py           # portfolio, open/close trades, cost model
        resolver.py        # closes trades + resolves forecasts at horizon
    tests/
  frontend/                # Vite + React + TS dashboard (polls /api)
```

**Stack:** Python 3.11+, FastAPI, SQLAlchemy 2.0 async + SQLite (aiosqlite), httpx, feedparser, APScheduler, Anthropic SDK (structured outputs via `client.messages.parse`). Frontend: Vite/React/TS, dev proxy `/api` → `:8000`.

---

## 3. Signal lifecycle

1. **Ingest** (scheduled): RSS / EDGAR pollers create `Event` rows, deduped by `content_hash`. Both `published_at` (source claim) and `fetched_at` (our clock, UTC) are stored — the gap is our honest latency measurement. Market pollers store `MarketSnapshot` (price, funding, OI per asset) and `OddsSnapshot` (Polymarket).
2. **Analyze** (scheduled): unprocessed events go to the analyst with a compact market-context block (latest prices, funding, top Polymarket odds). The analyst returns a `ForecastOutput` (schema-validated). Non-relevant events get `is_market_relevant=false` and are marked processed — most news is noise and the prompt says so.
3. **Filter → Trade**: a forecast becomes a paper trade only if ALL pass:
   - `is_market_relevant` and `direction != "none"`
   - `probability >= min_probability` (default 0.60)
   - if a market prior exists: `probability − prior >= min_edge_to_trade` (default 0.05)
   - funding veto: don't enter in the direction of crowded positioning when |funding| > threshold
   - notional from `kelly_size()` > 0
4. **Resolve** (scheduled): when `entry_ts + horizon` passes, the resolver closes the trade at current price (cost model applied) and resolves the forecast: `outcome = 1` if the signed return matched the predicted direction, `brier = (probability − outcome)²`.
5. **Learn**: `/api/calibration` aggregates Brier and hit-rate per category. When a category proves miscalibrated over N≥30 resolved forecasts, its forecasts get downweighted (phase 1: surfaced in dashboard; phase 2: automatic Platt scaling per category).

## 4. Sizing & risk (deterministic — never the LLM)

For a directional bet with calibrated probability `p` and symmetric payoff:

```
raw_kelly  = 2p − 1                          # Kelly fraction for even-odds binary
fraction   = kelly_fraction * raw_kelly      # quarter-Kelly default (0.25)
notional   = min(fraction, max_position_frac) * equity   # cap 10% default
```

Cost model: `fee_bps` (default 10) round trip — half charged at entry, half at exit, on notional. PnL for a closed trade: `sign * (exit−entry)/entry * notional − fees` where sign = +1 long / −1 short. Cash is adjusted at close; equity = cash + unrealized PnL of open trades.

Funding veto: if 8h funding rate > `+funding_veto_abs`, block new longs (crowded long); if < −threshold, block new shorts.

## 4b. Model cascade & shadow scoring (added 2026-06-10)

LLM cost must scale with **decisions, not event volume** — and model quality must be a *measured fact*, not a guess.

```
event → Triage (haiku): is_market_relevant?          ~90% die here, ~$0.40/day
      → Analysis (sonnet): full ForecastOutput        survivors only, ~$0.50/day
      → Escalation (opus): re-analyze IF              ~$0.20/day
           p >= min_probability − escalation_margin (a trade is near), OR
           category ∈ escalation_categories (macro, regulation, hack_security, etf_flow)
        · escalated forecast becomes canonical (stage="escalation")
        · the sonnet forecast is kept as a paired shadow — free comparison data
        · ensemble veto: if the two models disagree on direction, no trade
      → Shadow sampling: shadow_rate of analyzed events also scored by the
        other models (stage="shadow", never traded, Brier-scored identically)
```

`Forecast.shadow=True` rows are excluded from `/api/calibration` (which measures the trading system) and included in `/api/models` (which measures the models). `/api/models` is restricted to the **paired subset** — events scored by ≥2 distinct models — because pooling would confound model skill with event selection (escalations are high-conviction by construction). After ~100+ resolved pairs it answers empirically whether the cheap model is costing alpha — and in which categories.

**Fill honesty:** `price_at_forecast` and paper-trade entry prices are fetched **live at decision time** (batch snapshot only as fallback) — a batch's market context can be minutes stale after the cascade's sequential LLM calls, and stamping fills with it would book pre-decision movement as instant PnL. Concurrent `analyze_pending` invocations are lock-rejected to prevent double-processing.

**Price-action context:** the analyst receives, per asset, 1h/24h/7d returns, daily-ized 24h realized vol, and position in the 7d range (from Binance hourly klines) — without these it cannot honestly judge "is this already priced in?". **Regime tags:** every forecast is stamped with `classify_regime(ret_7d, vol_24h)` (e.g. `up/high_vol`) so calibration can later be conditioned on regime.

## 5. Data sources (MVP — all free, verified live 2026-06-10)

| Source | What | Endpoint |
|---|---|---|
| RSS ×5 | News + Trump posts | CoinDesk `coindesk.com/arc/outboundfeeds/rss`, The Block `theblock.co/rss.xml`, Cointelegraph `cointelegraph.com/rss`, Decrypt `decrypt.co/feed`, TrumpsTruth `trumpstruth.org/feed` |
| Binance spot | Prices | `api.binance.com/api/v3/ticker/price?symbol=BTCUSDT` |
| Binance futures | Funding, OI | `fapi.binance.com/fapi/v1/premiumIndex`, `/fapi/v1/openInterest` |
| Polymarket Gamma | Event odds (priors) | `gamma-api.polymarket.com/markets` (public, no auth) |
| SEC EDGAR FTS | Crypto filings | `efts.sec.gov/LATEST/search-index?q=...&forms=...` — **must send User-Agent with contact email**; ≤10 req/s |

Phase 1 additions: token-unlock calendar, Kalshi, Bybit announcements, DefiLlama stablecoin supply, FRED macro calendar.

## 6. Interface contract (builders MUST match exactly)

```python
# ingest/base.py
def content_hash(*parts: str) -> str
async def store_events(session, events: list[dict]) -> int   # dicts match Event columns; dedupe on content_hash; returns inserted count

# ingest/rss.py
FEEDS: list[tuple[str, str]]                                  # (source_name, url)
async def ingest_rss(session) -> int

# ingest/prices.py
async def fetch_price(symbol: str) -> float                   # symbol like "BTCUSDT"
async def snapshot_markets(session) -> None                   # one MarketSnapshot per settings.assets

# ingest/derivs.py
async def fetch_funding(symbol: str) -> float | None
async def fetch_open_interest(symbol: str) -> float | None

# ingest/polymarket.py
async def ingest_polymarket(session) -> int                   # stores OddsSnapshot rows

# ingest/edgar.py
async def ingest_edgar(session) -> int                        # stores Events, source="sec_edgar", category="filing"

# analysis/analyst.py
def analyze_event_sync(event_payload: dict, market_context: dict) -> ForecastOutput | None
async def analyze_event(event_payload: dict, market_context: dict) -> ForecastOutput | None  # asyncio.to_thread wrapper

# analysis/calibration.py
def brier(probability: float, outcome: int) -> float
async def calibration_report(session) -> list[dict]           # per-category: {category, n, mean_brier, hit_rate, mean_probability}

# trading/sizing.py
def kelly_size(probability: float, equity: float, kelly_fraction: float, max_frac: float) -> float  # returns notional, 0 if p <= 0.5
def funding_veto(direction: str, funding_rate: float | None, threshold: float) -> bool              # True = blocked

# trading/paper.py
async def get_portfolio(session) -> Portfolio                 # creates singleton row (id=1) with settings.starting_cash if missing
async def compute_equity(session) -> float                    # cash + unrealized PnL (current prices via fetch_price)
async def open_trade(session, forecast, price: float, notional: float) -> Trade
async def close_trade(session, trade, exit_price: float) -> Trade

# trading/resolver.py
async def resolve_due(session) -> int                         # closes due trades + resolves their forecasts; returns count

# pipeline.py
async def analyze_pending(limit: int = 10) -> int             # full step 2-3 of lifecycle; opens its own session

# scheduler.py
def create_scheduler() -> AsyncIOScheduler                    # all jobs wired, not started

# api/routes.py
router = APIRouter()  # GET /events, /forecasts, /trades, /portfolio, /calibration; POST /run/ingest, /run/analyze
```

All timestamps: naive UTC (`datetime.utcnow()`). All DB access through `db.session_scope()` or an injected session.

## 7. Roadmap

- **Phase 0 (this scaffold):** end-to-end loop live on paper. Goal: forecasts flowing within a day.
- **Phase 1:** token-unlock calendar (the proven edge), Kalshi priors, macro-print no-trade calendar (FRED/static YAML), dashboard polish, anonymized-headline option (reduces LLM "distraction effect").
- **Phase 2:** per-category Platt scaling once n≥30/category; reaction-profile dataset analysis; governance-forum diffing ("Lazy Prices for DAOs").
- **Phase 3 (≥6 months of ledger):** statistical models on our own forward-collected dataset — the only uncontaminated dataset we can ever have.

## 8. Non-goals

No backtesting (unfalsifiable). No real money until ≥6 months of positive calibrated paper results. No HFT/listing-pop chasing. No leverage modeling beyond notional caps. No X/Twitter scraping in MVP (ToS + cost).

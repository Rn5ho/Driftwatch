# DriftWatch — project instructions

News-driven crypto **paper-trading** research system. **`SPEC.md` is the source of truth** — read it before changing pipeline, trading, or analysis code. Its section 6 is the inter-module interface contract; section 4b is the model cascade.

## Non-negotiable design principles

- **Forward-only.** No backtests, ever (LLM training contamination makes them unfalsifiable). The forward forecast ledger is the product.
- **The LLM never sizes positions.** Models output calibrated probabilities; sizing/vetoes are deterministic code (`trading/sizing.py`).
- **Honest data.** Fill prices fetched live at decision time; dual timestamps (`published_at` vs `fetched_at`); cost model on every paper fill; voided forecasts excluded, not faked.
- **No DB transaction may span an LLM or HTTP call.** SQLite has one writer; the pipeline does LLM work sessionless, then writes in short transactions. Keep it that way.
- **Frozen prompts.** Never interpolate anything dynamic into `analysis/prompts.py` constants.
- **LLM failures must not consume the queue** — events stay unprocessed with `attempts` retry/poison-guard semantics (`pipeline.py`).
- All timestamps: naive UTC via `datetime.utcnow()` (known deprecation, accepted for now — change only project-wide).

## Commands

```bash
# Backend (requires Python 3.11+; system python3 may be too old — use uv)
cd backend
uv venv --python 3.12 .venv && uv pip install -r requirements.txt   # if .venv missing
.venv/bin/python -m pytest tests -q                                  # run tests (must stay green)
.venv/bin/python -c "from app.main import app"                       # import smoke check
.venv/bin/uvicorn app.main:app --reload                              # run locally (needs backend/.env with ANTHROPIC_API_KEY)

# Frontend (Node 20; on the original dev Mac it lives at ~/.local/node/bin, not on PATH)
cd frontend && npm install && npm run build                          # tsc strict + vite
```

After any backend change: run pytest AND the import check. After frontend changes: `npm run build` (strict tsc is the type gate).

## Architecture in one breath

Scheduler (APScheduler, `app/scheduler.py`) ingests RSS/EDGAR/Polymarket/Binance → `app/pipeline.py` runs the cascade per event (Haiku triage → Sonnet analysis → Opus escalation near trades, plus shadow scoring) → deterministic trade filters → paper trades (`trading/paper.py`) → resolver Brier-scores everything at horizon (`trading/resolver.py`). Every decision lands in the `activity` table; every LLM call (with real token cost) in `llm_calls`; ledger invariants in `analysis/audit.py` surface at `/api/ops/audit`. Dashboard: React/Vite in `frontend/`, served by the backend from `backend/static/` in Docker.

## Deployment

Single Docker container (`Dockerfile` + `docker-compose.yml`), SQLite persisted in `./data/`. See `DEPLOY.md`. Production runs 24/7 on a Hetzner VPS — **host details, IPs, and access live in `CLAUDE.local.md` (not committed)**. The canonical ledger is the VPS copy, NOT any local `driftwatch.db`. Never run a second scheduler against the same queue/ledger.

## Costs

Runtime LLM spend goes on the user's own Anthropic API key (`backend/.env`). The cascade keeps it ~$1–1.5/day; check `/api/ops/costs` before and after changes that alter call volume. Don't add LLM calls per event without considering the multiplier.

## Roadmap (SPEC section 7)

Phase 1 next: token-unlock calendar (best-evidenced edge), Polymarket/Kalshi prior matching (activates the expectation-gap filter — `market_prior` is currently always None), macro no-trade calendar, dead-man alerting. Phase 2: per-category Platt scaling once n≥30/category.

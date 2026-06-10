# DriftWatch

News-driven crypto **paper-trading** system that competes on reading, patience, and calibration — never speed. See `SPEC.md` for the full design and the research behind it.

The LLM produces calibrated probability forecasts; position sizing is deterministic code (fractional Kelly + caps + funding veto). Every forecast is a timestamped, falsifiable record that gets Brier-scored at its horizon — that ledger is the self-learning loop.

## Run

```bash
# Backend — requires Python 3.11+ (system python3 on this Mac is 3.9, which won't work).
# A ready .venv (Python 3.12 via uv) already exists; to recreate it:
#   uv venv --python 3.12 .venv && uv pip install -r requirements.txt
cd backend
source .venv/bin/activate
cp .env.example .env   # add your ANTHROPIC_API_KEY
uvicorn app.main:app --reload

# Frontend (separate terminal)
cd frontend
npm install
npm run dev            # http://localhost:5173, proxies /api → :8000
```

The scheduler starts with the API: RSS/EDGAR/Polymarket/market ingestion, analysis of pending events, and trade/forecast resolution all run on intervals (see `app/config.py`).

Manual triggers: `POST /api/run/ingest`, `POST /api/run/analyze`.

For 24/7 operation on the Hetzner VPS (Docker, single container, SSH-tunnel access), see `DEPLOY.md`.

## Cost note

The analyst calls the Claude API at runtime (billed separately from any Claude subscription). Default model is `claude-opus-4-8`; set `DRIFTWATCH_ANALYST_MODEL=claude-haiku-4-5` in `backend/.env` for cheap mode. At hobby volume (tens of events/day, short prompts) expect cents-to-low-dollars per day on Opus, much less on Haiku.

## Status

Phase 0 scaffold (2026-06-10). Paper only. No real money until ≥6 months of positive, calibrated paper results.

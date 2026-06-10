"""HTTP API. All endpoints open their own session via session_scope().
Returns plain dicts/lists; FastAPI's encoder handles datetimes.
"""

import logging
from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter
from sqlalchemy import func, select
from sqlalchemy.inspection import inspect as sa_inspect

from app.analysis.audit import run_audit
from app.analysis.calibration import calibration_report, model_comparison
from app.db import session_scope
from app.ingest.edgar import ingest_edgar
from app.ingest.polymarket import ingest_polymarket
from app.ingest.prices import snapshot_markets
from app.ingest.rss import ingest_rss
from app.models import Activity, Event, Forecast, LlmCall, MarketSnapshot, Trade
from app.pipeline import analyze_pending
from app.trading.paper import compute_equity, get_portfolio

logger = logging.getLogger(__name__)

router = APIRouter()


def _to_dict(obj: Any) -> dict[str, Any]:
    """ORM row -> plain dict of all mapped columns."""
    return {attr.key: getattr(obj, attr.key) for attr in sa_inspect(obj).mapper.column_attrs}


@router.get("/events")
async def list_events(limit: int = 50) -> list[dict[str, Any]]:
    async with session_scope() as session:
        rows = (
            await session.execute(
                select(Event).order_by(Event.fetched_at.desc(), Event.id.desc()).limit(limit)
            )
        ).scalars().all()
        return [
            {
                "id": e.id,
                "source": e.source,
                "category": e.category,
                "title": e.title,
                "url": e.url,
                "published_at": e.published_at,
                "fetched_at": e.fetched_at,
                "processed": e.processed,
            }
            for e in rows
        ]


@router.get("/forecasts")
async def list_forecasts(limit: int = 50) -> list[dict[str, Any]]:
    async with session_scope() as session:
        rows = (
            await session.execute(
                select(Forecast).order_by(Forecast.created_at.desc(), Forecast.id.desc()).limit(limit)
            )
        ).scalars().all()
        return [_to_dict(f) for f in rows]


@router.get("/trades")
async def list_trades(limit: int = 50) -> list[dict[str, Any]]:
    async with session_scope() as session:
        rows = (
            await session.execute(
                select(Trade).order_by(Trade.entry_ts.desc(), Trade.id.desc()).limit(limit)
            )
        ).scalars().all()
        return [_to_dict(t) for t in rows]


@router.get("/portfolio")
async def portfolio() -> dict[str, Any]:
    async with session_scope() as session:
        pf = await get_portfolio(session)
        equity = await compute_equity(session)
        open_trades = (
            await session.execute(
                select(func.count(Trade.id)).where(Trade.status == "open")
            )
        ).scalar_one()
        closed_trades = (
            await session.execute(
                select(func.count(Trade.id)).where(Trade.status == "closed")
            )
        ).scalar_one()
        realized_pnl = (
            await session.execute(
                select(func.coalesce(func.sum(Trade.pnl), 0.0)).where(Trade.status == "closed")
            )
        ).scalar_one()
        total_fees = (
            await session.execute(select(func.coalesce(func.sum(Trade.fees), 0.0)))
        ).scalar_one()
        return {
            "cash": pf.cash,
            "starting_cash": pf.starting_cash,
            "equity": equity,
            "open_trades": open_trades,
            "closed_trades": closed_trades,
            "realized_pnl": realized_pnl,
            "total_fees": total_fees,
        }


@router.get("/calibration")
async def calibration() -> list[dict[str, Any]]:
    async with session_scope() as session:
        return await calibration_report(session)


@router.get("/models")
async def models() -> list[dict[str, Any]]:
    """Per-model Brier comparison (shadows included) — is the cheap model
    costing us alpha?"""
    async with session_scope() as session:
        return await model_comparison(session)


@router.get("/ops/status")
async def ops_status() -> dict[str, Any]:
    """Health-at-a-glance: queue depth, triage pass-rate, costs, freshness."""
    async with session_scope() as session:
        day_ago = datetime.utcnow() - timedelta(hours=24)

        async def _scalar(stmt) -> Any:
            return (await session.execute(stmt)).scalar_one()

        unprocessed = await _scalar(select(func.count(Event.id)).where(Event.processed.is_(False)))
        events_24h = await _scalar(select(func.count(Event.id)).where(Event.fetched_at >= day_ago))
        triaged = await _scalar(select(func.count(Event.id)).where(Event.triage_relevant.is_not(None)))
        triage_passed = await _scalar(select(func.count(Event.id)).where(Event.triage_relevant.is_(True)))
        stage_rows = (
            await session.execute(
                select(Forecast.stage, func.count(Forecast.id)).group_by(Forecast.stage)
            )
        ).all()
        cost_total = await _scalar(select(func.coalesce(func.sum(LlmCall.cost_usd), 0.0)))
        cost_24h = await _scalar(
            select(func.coalesce(func.sum(LlmCall.cost_usd), 0.0)).where(LlmCall.ts >= day_ago)
        )
        last_event = await _scalar(select(func.max(Event.fetched_at)))
        last_snapshot = await _scalar(select(func.max(MarketSnapshot.ts)))
        last_activity = await _scalar(select(func.max(Activity.ts)))
        open_trades = await _scalar(select(func.count(Trade.id)).where(Trade.status == "open"))

        return {
            "unprocessed_events": unprocessed,
            "events_24h": events_24h,
            "triage_pass_rate": round(triage_passed / triaged, 4) if triaged else None,
            "forecasts_by_stage": {stage: count for stage, count in stage_rows},
            "cost_total_usd": round(cost_total, 4),
            "cost_24h_usd": round(cost_24h, 4),
            "last_event_at": last_event,
            "last_snapshot_at": last_snapshot,
            "last_activity_at": last_activity,
            "open_trades": open_trades,
        }


@router.get("/ops/activity")
async def ops_activity(limit: int = 100) -> list[dict[str, Any]]:
    """The decision feed — the system narrating what it did and why."""
    async with session_scope() as session:
        rows = (
            await session.execute(
                select(Activity).order_by(Activity.ts.desc(), Activity.id.desc()).limit(limit)
            )
        ).scalars().all()
        return [_to_dict(a) for a in rows]


@router.get("/ops/costs")
async def ops_costs() -> dict[str, Any]:
    """Real LLM spend from token usage, grouped by model and role."""
    async with session_scope() as session:
        by_model = (
            await session.execute(
                select(
                    LlmCall.model,
                    func.count(LlmCall.id),
                    func.coalesce(func.sum(LlmCall.input_tokens), 0),
                    func.coalesce(func.sum(LlmCall.output_tokens), 0),
                    func.coalesce(func.sum(LlmCall.cost_usd), 0.0),
                ).group_by(LlmCall.model)
            )
        ).all()
        by_role = (
            await session.execute(
                select(
                    LlmCall.role,
                    func.count(LlmCall.id),
                    func.coalesce(func.sum(LlmCall.cost_usd), 0.0),
                ).group_by(LlmCall.role)
            )
        ).all()
        return {
            "by_model": [
                {
                    "model": model,
                    "calls": calls,
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "cost_usd": round(cost, 4),
                }
                for model, calls, input_tokens, output_tokens, cost in by_model
            ],
            "by_role": [
                {"role": role, "calls": calls, "cost_usd": round(cost, 4)}
                for role, calls, cost in by_role
            ],
        }


@router.get("/ops/audit")
async def ops_audit() -> list[dict[str, Any]]:
    """Ledger invariants — every row should be ok=true, always."""
    async with session_scope() as session:
        return await run_audit(session)


@router.post("/run/ingest")
async def run_ingest() -> dict[str, Any]:
    """Run all ingest jobs now. Each gets its own session so one failure
    cannot roll back another's work."""
    results: dict[str, Any] = {}

    try:
        async with session_scope() as session:
            results["rss"] = await ingest_rss(session)
    except Exception:
        logger.exception("manual ingest_rss failed")
        results["rss"] = "error"

    try:
        async with session_scope() as session:
            await snapshot_markets(session)
        results["markets"] = "ok"
    except Exception:
        logger.exception("manual snapshot_markets failed")
        results["markets"] = "error"

    try:
        async with session_scope() as session:
            results["polymarket"] = await ingest_polymarket(session)
    except Exception:
        logger.exception("manual ingest_polymarket failed")
        results["polymarket"] = "error"

    try:
        async with session_scope() as session:
            results["edgar"] = await ingest_edgar(session)
    except Exception:
        logger.exception("manual ingest_edgar failed")
        results["edgar"] = "error"

    return results


@router.post("/run/analyze")
async def run_analyze() -> dict[str, int]:
    created = await analyze_pending()
    return {"forecasts_created": created}

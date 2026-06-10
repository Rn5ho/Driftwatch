"""Resolve trades and forecasts whose horizon has passed.

Closes due open trades at current price (cost model applied) and resolves
their forecasts with an outcome and Brier score. Also resolves UNTRADED
forecasts (filtered out by probability/edge/veto/sizing) — calibration must
include the forecasts we chose not to trade.
"""

import logging
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.activity import log_activity
from app.models import Forecast, Trade
from app.trading.paper import close_trade

logger = logging.getLogger(__name__)


def _void_forecast(session: AsyncSession, forecast: Forecast, reason: str) -> None:
    """Terminal state for forecasts that can never be scored (no reference
    price, or directional with asset NONE). Without it they are retried — with
    a live price fetch each — every cycle, forever. outcome stays None, so
    calibration and model comparison exclude them."""
    forecast.resolved_at = datetime.utcnow()
    log_activity(
        session, "resolve_void", reason,
        event_id=forecast.event_id, forecast_id=forecast.id,
    )


def _resolve_forecast(forecast: Forecast, exit_price: float, fallback_basis: float | None) -> bool:
    """Score a forecast against the realized price. Returns True if resolved."""
    basis = forecast.price_at_forecast if forecast.price_at_forecast is not None else fallback_basis
    if not basis:
        logger.warning("Forecast %s has no reference price; cannot resolve", forecast.id)
        return False

    signed_return = (exit_price - basis) / basis
    outcome = (
        1
        if (
            (forecast.direction == "long" and signed_return > 0)
            or (forecast.direction == "short" and signed_return < 0)
        )
        else 0
    )
    forecast.price_at_resolution = exit_price
    forecast.outcome = outcome
    forecast.brier = (forecast.probability - outcome) ** 2
    forecast.resolved_at = datetime.utcnow()
    return True


async def resolve_due(session: AsyncSession) -> int:
    """Close due open trades and resolve their forecasts; also resolve due
    untraded forecasts. Returns the number of forecasts resolved."""
    # Local import to avoid import cycles (per interface contract).
    from app.ingest.prices import fetch_price

    now = datetime.utcnow()
    resolved = 0

    # 1) Open trades past their forecast horizon.
    result = await session.execute(select(Trade).where(Trade.status == "open"))
    for trade in result.scalars().all():
        forecast = await session.get(Forecast, trade.forecast_id)
        if forecast is None:
            logger.warning("Open trade %s references missing forecast %s; skipping", trade.id, trade.forecast_id)
            continue
        if now < trade.entry_ts + timedelta(hours=forecast.horizon_hours):
            continue
        try:
            price = await fetch_price(f"{trade.asset}USDT")
        except Exception:
            logger.exception(
                "resolve_due: could not fetch price for %s (trade %s); will retry next cycle",
                trade.asset,
                trade.id,
            )
            continue
        await close_trade(session, trade, price)
        log_activity(
            session, "trade_close",
            f"closed {trade.side} {trade.asset} pnl={trade.pnl:+.2f} (fees={trade.fees:.2f}) @ {price:.4f}",
            event_id=forecast.event_id, forecast_id=forecast.id, trade_id=trade.id,
        )
        if _resolve_forecast(forecast, price, fallback_basis=trade.entry_price):
            log_activity(
                session, "resolve",
                f"{forecast.asset} {forecast.direction} p={forecast.probability:.2f} -> "
                f"outcome={forecast.outcome} brier={forecast.brier:.3f}",
                event_id=forecast.event_id, forecast_id=forecast.id, trade_id=trade.id,
            )
            resolved += 1

    # 2) Untraded directional forecasts past their horizon — calibration
    #    must include the bets we declined.
    traded_forecast_ids = select(Trade.forecast_id)
    result = await session.execute(
        select(Forecast).where(
            Forecast.direction != "none",
            Forecast.resolved_at.is_(None),
            Forecast.id.not_in(traded_forecast_ids),
        )
    )
    for forecast in result.scalars().all():
        if now < forecast.created_at + timedelta(hours=forecast.horizon_hours):
            continue
        if forecast.asset == "NONE":
            _void_forecast(session, forecast, "directional forecast with asset NONE — voided")
            continue
        if forecast.price_at_forecast is None:
            # Check the basis BEFORE spending a price fetch on a forecast that
            # can never resolve.
            _void_forecast(session, forecast, "no reference price recorded — voided")
            continue
        try:
            price = await fetch_price(f"{forecast.asset}USDT")
        except Exception:
            logger.exception(
                "resolve_due: could not fetch price for %s (forecast %s); will retry next cycle",
                forecast.asset,
                forecast.id,
            )
            continue
        if _resolve_forecast(forecast, price, fallback_basis=None):
            log_activity(
                session, "resolve",
                f"{forecast.asset} {forecast.direction} p={forecast.probability:.2f} -> "
                f"outcome={forecast.outcome} brier={forecast.brier:.3f} (untraded)",
                event_id=forecast.event_id, forecast_id=forecast.id,
            )
            resolved += 1

    return resolved

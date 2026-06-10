"""Paper portfolio and trade lifecycle with an explicit cost model.

Cost model: ``settings.fee_bps`` round trip — half charged on notional at
entry, half at exit. Cash is NOT deducted at entry (notional is margin-free
paper exposure); PnL and all fees settle into cash at close.
"""

import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import Forecast, Portfolio, Trade

logger = logging.getLogger(__name__)


def _half_fee(notional: float) -> float:
    """One leg (entry or exit) of the round-trip cost model."""
    return notional * (settings.fee_bps / 2.0) / 10_000.0


async def get_portfolio(session: AsyncSession) -> Portfolio:
    """Return the singleton portfolio row (id=1), creating it if missing.

    Two concurrent sessions can both observe the row missing on first touch;
    the insert runs in a savepoint so the loser re-selects instead of rolling
    back its whole transaction.
    """
    result = await session.execute(select(Portfolio).where(Portfolio.id == 1))
    portfolio = result.scalar_one_or_none()
    if portfolio is None:
        try:
            async with session.begin_nested():
                portfolio = Portfolio(
                    id=1,
                    starting_cash=settings.starting_cash,
                    cash=settings.starting_cash,
                )
                session.add(portfolio)
                await session.flush()
        except IntegrityError:
            result = await session.execute(select(Portfolio).where(Portfolio.id == 1))
            portfolio = result.scalar_one()
    return portfolio


async def open_trade(session: AsyncSession, forecast: Forecast, price: float, notional: float) -> Trade:
    """Open a paper trade for a forecast. Entry fee accrues on the trade row."""
    entry_fee = _half_fee(notional)
    trade = Trade(
        forecast_id=forecast.id,
        asset=forecast.asset,
        side=forecast.direction,
        notional=notional,
        entry_price=price,
        fees=entry_fee,
        status="open",
    )
    session.add(trade)
    await session.flush()
    return trade


async def close_trade(session: AsyncSession, trade: Trade, exit_price: float) -> Trade:
    """Close a paper trade: apply exit fee, realize PnL, settle into cash."""
    exit_fee = _half_fee(trade.notional)
    sign = 1.0 if trade.side == "long" else -1.0
    gross = sign * (exit_price - trade.entry_price) / trade.entry_price * trade.notional

    trade.pnl = round(gross - trade.fees - exit_fee, 2)
    trade.fees = round(trade.fees + exit_fee, 2)
    trade.exit_price = exit_price
    trade.exit_ts = datetime.utcnow()
    trade.status = "closed"

    portfolio = await get_portfolio(session)
    portfolio.cash += trade.pnl
    portfolio.updated_at = datetime.utcnow()
    await session.flush()
    return trade


async def compute_equity(session: AsyncSession) -> float:
    """Cash plus unrealized PnL of open trades at current prices, NET of fees
    already accrued on the open trades (SPEC: half the fee is charged at
    entry — equity must reflect it, or sizing is systematically too large).

    Prices are fetched once per distinct asset. Per-asset failures are logged
    and that asset's unrealized PnL is treated as 0 — equity reporting must
    never crash the scheduler.
    """
    # Local import to avoid import cycles (per interface contract).
    from app.ingest.prices import fetch_price

    portfolio = await get_portfolio(session)
    equity = portfolio.cash

    result = await session.execute(select(Trade).where(Trade.status == "open"))
    trades = list(result.scalars().all())

    prices: dict[str, float] = {}
    for asset in {t.asset for t in trades}:
        try:
            prices[asset] = await fetch_price(f"{asset}USDT")
        except Exception:
            logger.exception(
                "compute_equity: could not fetch price for %s; treating its unrealized PnL as 0",
                asset,
            )

    for trade in trades:
        current = prices.get(trade.asset)
        if current is None:
            continue
        sign = 1.0 if trade.side == "long" else -1.0
        gross = sign * (current - trade.entry_price) / trade.entry_price * trade.notional
        equity += gross - trade.fees
    return equity

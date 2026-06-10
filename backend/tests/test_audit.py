"""Ledger-audit invariant tests: a consistent ledger passes, corruption flags."""

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.analysis.audit import run_audit
from app.db import Base
from app.models import Forecast, Portfolio, Trade


@pytest_asyncio.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        yield s
    await engine.dispose()


async def _seed_consistent(session) -> Forecast:
    """Portfolio + one closed trade + its resolved forecast, all consistent.

    entry 100 -> exit 110, long, notional 1000, fee_bps 10:
    fees 1.00 total, gross 100.00, pnl 99.00, cash 10000 + 99 = 10099.
    """
    session.add(Portfolio(id=1, starting_cash=10_000.0, cash=10_099.0))
    forecast = Forecast(
        id=1, event_id=1, asset="BTC", category="macro", direction="long",
        probability=0.7, horizon_hours=24, price_at_forecast=100.0,
        outcome=1, brier=(0.7 - 1) ** 2, price_at_resolution=110.0,
    )
    from datetime import datetime

    forecast.resolved_at = datetime.utcnow()
    session.add(forecast)
    session.add(
        Trade(
            id=1, forecast_id=1, asset="BTC", side="long", notional=1000.0,
            entry_price=100.0, exit_price=110.0, fees=1.0, pnl=99.0,
            status="closed", exit_ts=datetime.utcnow(),
        )
    )
    await session.flush()
    return forecast


def _by_check(rows: list[dict]) -> dict[str, dict]:
    return {r["check"]: r for r in rows}


@pytest.mark.asyncio
async def test_clean_ledger_passes(session):
    await _seed_consistent(session)
    rows = _by_check(await run_audit(session))
    assert all(r["ok"] for r in rows.values()), rows


@pytest.mark.asyncio
async def test_cash_drift_flagged(session):
    await _seed_consistent(session)
    portfolio = await session.get(Portfolio, 1)
    portfolio.cash += 50.0  # money out of thin air
    rows = _by_check(await run_audit(session))
    assert not rows["cash_equation"]["ok"]


@pytest.mark.asyncio
async def test_wrong_pnl_flagged(session):
    await _seed_consistent(session)
    trade = await session.get(Trade, 1)
    trade.pnl = 120.0  # inconsistent with prices/fees
    rows = _by_check(await run_audit(session))
    assert not rows["closed_trade_math"]["ok"]


@pytest.mark.asyncio
async def test_wrong_brier_flagged(session):
    forecast = await _seed_consistent(session)
    forecast.brier = 0.5
    rows = _by_check(await run_audit(session))
    assert not rows["resolution_integrity"]["ok"]


@pytest.mark.asyncio
async def test_duplicate_canonical_flagged(session):
    await _seed_consistent(session)
    session.add(
        Forecast(
            id=2, event_id=1, asset="BTC", category="macro", direction="short",
            probability=0.6, horizon_hours=24, shadow=False,
        )
    )
    await session.flush()
    rows = _by_check(await run_audit(session))
    assert not rows["single_canonical_per_event"]["ok"]


@pytest.mark.asyncio
async def test_trade_on_shadow_flagged(session):
    forecast = await _seed_consistent(session)
    forecast.shadow = True
    rows = _by_check(await run_audit(session))
    assert not rows["trade_forecast_link"]["ok"]

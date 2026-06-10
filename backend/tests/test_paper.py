"""Paper-trading lifecycle tests against a fresh in-memory SQLite database.

Each test builds its own engine/sessionmaker ("sqlite+aiosqlite:///:memory:")
and never touches the global app database. Settings are monkeypatched for
deterministic cost-model numbers.
"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.db import Base
from app.models import Forecast
from app.trading.paper import close_trade, get_portfolio, open_trade

pytestmark = pytest.mark.asyncio


async def _make_sessionmaker() -> async_sessionmaker[AsyncSession]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


def _forecast(direction: str = "long") -> Forecast:
    return Forecast(
        asset="BTC",
        category="macro",
        direction=direction,
        probability=0.7,
        horizon_hours=24,
        price_at_forecast=100.0,
    )


async def test_get_portfolio_creates_singleton(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "starting_cash", 10_000.0)
    maker = await _make_sessionmaker()
    async with maker() as session:
        portfolio = await get_portfolio(session)
        assert portfolio.id == 1
        assert portfolio.starting_cash == 10_000.0
        assert portfolio.cash == 10_000.0
        # Second call returns the same row, no duplicate.
        again = await get_portfolio(session)
        assert again.id == portfolio.id


async def test_long_round_trip_to_the_cent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "fee_bps", 10.0)
    monkeypatch.setattr(settings, "starting_cash", 10_000.0)
    maker = await _make_sessionmaker()
    async with maker() as session:
        forecast = _forecast("long")
        session.add(forecast)
        await session.flush()

        trade = await open_trade(session, forecast, price=100.0, notional=1000.0)
        # Entry fee: 1000 * (10/2)/10000 = 0.50; cash untouched at entry.
        assert trade.side == "long"
        assert trade.asset == "BTC"
        assert trade.forecast_id == forecast.id
        assert trade.entry_price == 100.0
        assert trade.notional == 1000.0
        assert trade.fees == pytest.approx(0.50)
        assert trade.status == "open"
        assert trade.pnl is None
        portfolio = await get_portfolio(session)
        assert portfolio.cash == pytest.approx(10_000.00)

        trade = await close_trade(session, trade, exit_price=110.0)
        # Gross: (110-100)/100 * 1000 = 100.00; fees 0.50 + 0.50 = 1.00;
        # pnl = 100.00 - 1.00 = 99.00; cash = 10000 + 99.00 = 10099.00.
        assert trade.status == "closed"
        assert trade.exit_price == 110.0
        assert trade.exit_ts is not None
        assert trade.fees == pytest.approx(1.00)
        assert trade.pnl == pytest.approx(99.00)
        assert portfolio.cash == pytest.approx(10_099.00)


async def test_short_side_sign(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "fee_bps", 10.0)
    monkeypatch.setattr(settings, "starting_cash", 10_000.0)
    maker = await _make_sessionmaker()
    async with maker() as session:
        forecast = _forecast("short")
        session.add(forecast)
        await session.flush()

        trade = await open_trade(session, forecast, price=100.0, notional=1000.0)
        trade = await close_trade(session, trade, exit_price=90.0)
        # Short: gross = -1 * (90-100)/100 * 1000 = +100.00 -> pnl 99.00.
        assert trade.pnl == pytest.approx(99.00)
        assert trade.fees == pytest.approx(1.00)
        portfolio = await get_portfolio(session)
        assert portfolio.cash == pytest.approx(10_099.00)


async def test_losing_long_settles_negative(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "fee_bps", 10.0)
    monkeypatch.setattr(settings, "starting_cash", 10_000.0)
    maker = await _make_sessionmaker()
    async with maker() as session:
        forecast = _forecast("long")
        session.add(forecast)
        await session.flush()

        trade = await open_trade(session, forecast, price=100.0, notional=1000.0)
        trade = await close_trade(session, trade, exit_price=95.0)
        # Gross: -50.00; pnl = -50.00 - 1.00 = -51.00; cash 9949.00.
        assert trade.pnl == pytest.approx(-51.00)
        portfolio = await get_portfolio(session)
        assert portfolio.cash == pytest.approx(9_949.00)

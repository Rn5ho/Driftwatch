"""Binance spot prices, klines, price-action context, and market snapshots."""

import logging
import math

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.ingest.derivs import fetch_funding, fetch_open_interest
from app.models import MarketSnapshot

logger = logging.getLogger(__name__)

BINANCE = "https://api.binance.com"


async def fetch_price(symbol: str) -> float:
    """Spot price for a symbol like "BTCUSDT". Raises on failure (callers catch)."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(
            f"{BINANCE}/api/v3/ticker/price", params={"symbol": symbol}
        )
        resp.raise_for_status()
        data = resp.json()
        return float(data["price"])


async def fetch_klines(
    symbol: str, interval: str = "1h", limit: int = 168
) -> list[tuple[int, float]]:
    """(open_time_ms, close) pairs from Binance spot klines. Raises on failure."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(
            f"{BINANCE}/api/v3/klines",
            params={"symbol": symbol, "interval": interval, "limit": limit},
        )
        resp.raise_for_status()
        return [(int(k[0]), float(k[4])) for k in resp.json()]


_EMPTY_CONTEXT: dict[str, float | None] = {
    "ret_1h": None,
    "ret_24h": None,
    "ret_7d": None,
    "vol_24h": None,
    "range_pos_7d": None,
}


async def compute_price_context(symbol: str) -> dict[str, float | None]:
    """Price-action context from 7d of hourly closes.

    The analyst cannot judge "is this already priced in?" without knowing what
    price recently did. Returns recent returns, daily-ized realized vol, and
    the position of the current price within the 7d range (0=low, 1=high).
    All None on failure — an honest unknown.
    """
    try:
        # 169 candles: the last kline is the in-progress hour, so a true
        # 168h (7d) lookback needs one extra.
        closes = [close for _, close in await fetch_klines(symbol, limit=169)]
    except Exception:
        logger.exception("klines fetch failed for %s", symbol)
        return dict(_EMPTY_CONTEXT)
    if len(closes) < 26:
        return dict(_EMPTY_CONTEXT)

    last = closes[-1]

    def ret(hours: int) -> float | None:
        if len(closes) <= hours or closes[-1 - hours] == 0:
            return None
        return round((last - closes[-1 - hours]) / closes[-1 - hours], 5)

    log_returns = [
        math.log(closes[i] / closes[i - 1])
        for i in range(len(closes) - 24, len(closes))
        if closes[i - 1] > 0
    ]
    mean = sum(log_returns) / len(log_returns)
    variance = sum((r - mean) ** 2 for r in log_returns) / len(log_returns)
    vol_24h = round(math.sqrt(variance) * math.sqrt(24), 5)  # daily-ized

    high, low = max(closes), min(closes)
    range_pos = round((last - low) / (high - low), 4) if high > low else None

    return {
        "ret_1h": ret(1),
        "ret_24h": ret(24),
        # ret() returns None when history is short — an honest unknown beats
        # mislabeling a 25h return as a 7d trend for the regime classifier.
        "ret_7d": ret(168),
        "vol_24h": vol_24h,
        "range_pos_7d": range_pos,
    }


async def snapshot_markets(session: AsyncSession) -> None:
    """Store one MarketSnapshot per configured asset. Per-asset isolation."""
    for asset in settings.assets:
        symbol = f"{asset}USDT"
        try:
            price = await fetch_price(symbol)
            funding = await fetch_funding(symbol)
            open_interest = await fetch_open_interest(symbol)
            session.add(
                MarketSnapshot(
                    asset=asset,
                    price=price,
                    funding_rate=funding,
                    open_interest=open_interest,
                )
            )
        except Exception:
            logger.exception("Market snapshot failed for %s", asset)
    await session.flush()

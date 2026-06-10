"""Binance USD-M futures: funding rate and open interest. Both return None on
any error — positioning data is an enhancement, never a blocker."""

import logging

import httpx

logger = logging.getLogger(__name__)

FAPI = "https://fapi.binance.com"


async def fetch_funding(symbol: str) -> float | None:
    """Last funding rate for a perp symbol like "BTCUSDT"; None on any error."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{FAPI}/fapi/v1/premiumIndex", params={"symbol": symbol}
            )
            resp.raise_for_status()
            data = resp.json()
            return float(data["lastFundingRate"])
    except Exception:
        logger.warning("Funding fetch failed for %s", symbol, exc_info=True)
        return None


async def fetch_open_interest(symbol: str) -> float | None:
    """Open interest (base units) for a perp symbol; None on any error."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{FAPI}/fapi/v1/openInterest", params={"symbol": symbol}
            )
            resp.raise_for_status()
            data = resp.json()
            return float(data["openInterest"])
    except Exception:
        logger.warning("Open interest fetch failed for %s", symbol, exc_info=True)
        return None

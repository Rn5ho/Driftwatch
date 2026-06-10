"""Polymarket Gamma API odds — the measurement instrument for what's priced
in. Stored as time-series OddsSnapshot rows (no dedupe by design)."""

import json
import logging
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import OddsSnapshot

logger = logging.getLogger(__name__)

GAMMA_MARKETS = "https://gamma-api.polymarket.com/markets"


async def ingest_polymarket(session: AsyncSession) -> int:
    """Snapshot the top-volume open markets. Returns rows added; 0 on error."""
    try:
        async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
            resp = await client.get(
                GAMMA_MARKETS,
                params={
                    "closed": "false",
                    "order": "volumeNum",
                    "ascending": "false",
                    "limit": 25,
                },
            )
            resp.raise_for_status()
            markets = resp.json()

        if not isinstance(markets, list):
            logger.warning("Polymarket response was not a list: %r", type(markets))
            return 0

        added = 0
        for market in markets:
            try:
                slug: str = market.get("slug") or ""
                question: str = market.get("question") or ""

                prices: Any = market.get("outcomePrices")
                # Usually a JSON-encoded string like '["0.65", "0.35"]',
                # but may already be a list — handle both.
                if isinstance(prices, str):
                    prices = json.loads(prices)
                if not prices:
                    continue
                yes_price = float(prices[0])

                raw_volume = market.get("volumeNum", market.get("volume"))
                volume: float | None = (
                    float(raw_volume) if raw_volume is not None else None
                )

                session.add(
                    OddsSnapshot(
                        market_slug=slug,
                        question=question,
                        yes_price=yes_price,
                        volume=volume,
                    )
                )
                added += 1
            except Exception:
                logger.warning(
                    "Skipping malformed Polymarket market: %r",
                    market.get("slug", "<no slug>") if isinstance(market, dict) else market,
                    exc_info=True,
                )

        if added:
            await session.flush()
        return added
    except Exception:
        logger.exception("Polymarket ingest failed")
        return 0

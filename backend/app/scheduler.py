"""APScheduler wiring. Every job is an async wrapper that opens its own
session and try/except-logs — a failing poller must never crash the loop.
"""

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.config import settings
from app.db import session_scope
from app.ingest.edgar import ingest_edgar
from app.ingest.polymarket import ingest_polymarket
from app.ingest.prices import snapshot_markets
from app.ingest.rss import ingest_rss
from app.pipeline import analyze_pending
from app.trading.resolver import resolve_due

logger = logging.getLogger(__name__)


def _session_job(name: str, fn: Callable[..., Awaitable[Any]]) -> Callable[[], Awaitable[None]]:
    """Wrap an `async fn(session)` into a no-arg job with its own session and error logging."""

    async def job() -> None:
        try:
            async with session_scope() as session:
                result = await fn(session)
                logger.info("job %s done (result=%s)", name, result)
        except Exception:
            logger.exception("job %s failed", name)

    job.__name__ = f"job_{name}"
    return job


async def _analyze_job() -> None:
    """analyze_pending manages its own session and swallows errors; belt and braces here."""
    try:
        created = await analyze_pending()
        logger.info("job analyze_pending done (forecasts_created=%s)", created)
    except Exception:
        logger.exception("job analyze_pending failed")


def create_scheduler() -> AsyncIOScheduler:
    """Build the scheduler with all jobs wired. Caller starts it."""
    scheduler = AsyncIOScheduler()
    common: dict[str, Any] = {"coalesce": True, "max_instances": 1}

    scheduler.add_job(
        _session_job("ingest_rss", ingest_rss),
        "interval",
        seconds=settings.rss_poll_seconds,
        id="ingest_rss",
        **common,
    )
    scheduler.add_job(
        _session_job("snapshot_markets", snapshot_markets),
        "interval",
        seconds=settings.market_poll_seconds,
        id="snapshot_markets",
        **common,
    )
    scheduler.add_job(
        _session_job("ingest_polymarket", ingest_polymarket),
        "interval",
        seconds=settings.polymarket_poll_seconds,
        id="ingest_polymarket",
        **common,
    )
    scheduler.add_job(
        _session_job("ingest_edgar", ingest_edgar),
        "interval",
        seconds=settings.edgar_poll_seconds,
        id="ingest_edgar",
        **common,
    )
    scheduler.add_job(
        _analyze_job,
        "interval",
        seconds=settings.analyze_poll_seconds,
        id="analyze_pending",
        **common,
    )
    scheduler.add_job(
        _session_job("resolve_due", resolve_due),
        "interval",
        seconds=settings.resolver_poll_seconds,
        id="resolve_due",
        **common,
    )
    return scheduler

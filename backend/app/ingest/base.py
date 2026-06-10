"""Shared ingest helpers: content hashing and deduplicated Event storage."""

import hashlib
import logging

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Event

logger = logging.getLogger(__name__)

_SEPARATOR = "\x1f"  # unit separator — avoids accidental collisions when joining parts


def content_hash(*parts: str) -> str:
    """sha256 hex digest of the joined parts."""
    joined = _SEPARATOR.join(parts)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


async def store_events(session: AsyncSession, events: list[dict]) -> int:
    """Insert Event rows for dicts whose content_hash is not already stored.

    Each dict's keys match Event columns (source, category, title, summary,
    url, published_at, content_hash; fetched_at defaults). Existing hashes are
    looked up in a single SELECT. Returns the number of rows inserted.
    """
    if not events:
        return 0

    hashes = [e["content_hash"] for e in events if e.get("content_hash")]
    seen: set[str] = set()
    if hashes:
        result = await session.execute(
            select(Event.content_hash).where(Event.content_hash.in_(hashes))
        )
        seen = set(result.scalars().all())

    inserted = 0
    for event in events:
        h = event.get("content_hash")
        if not h or h in seen:
            continue
        seen.add(h)  # also dedupes within this batch
        # Per-row savepoint: a concurrent ingester (e.g. the manual endpoint
        # racing a scheduled job) inserting the same hash must skip one row,
        # not roll back the whole batch.
        try:
            async with session.begin_nested():
                session.add(Event(**event))
                await session.flush()
        except IntegrityError:
            logger.debug("content_hash raced in concurrently, skipping: %s", h)
            continue
        inserted += 1

    return inserted

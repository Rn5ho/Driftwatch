"""RSS ingestion — 5 feeds (crypto news + TrumpsTruth). Per-feed isolation:
one dead feed never kills the rest."""

import logging
from datetime import datetime

import feedparser
import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.ingest.base import content_hash, store_events

logger = logging.getLogger(__name__)

FEEDS: list[tuple[str, str]] = [
    ("coindesk", "https://www.coindesk.com/arc/outboundfeeds/rss"),
    ("theblock", "https://www.theblock.co/rss.xml"),
    ("cointelegraph", "https://cointelegraph.com/rss"),
    ("decrypt", "https://decrypt.co/feed"),
    ("trumpstruth", "https://www.trumpstruth.org/feed"),
]


async def ingest_rss(session: AsyncSession) -> int:
    """Fetch all feeds, parse entries into event dicts, store with dedupe.

    Returns the total number of new Event rows inserted.
    """
    events: list[dict] = []
    async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
        for name, url in FEEDS:
            try:
                resp = await client.get(url)
                resp.raise_for_status()
                parsed = feedparser.parse(resp.content)  # sync, fine here
                for entry in parsed.entries:
                    title: str = entry.get("title") or ""
                    link: str = entry.get("link") or ""
                    if not title:
                        continue

                    summary: str = (entry.get("summary") or "")[:2000]

                    published_at: datetime | None = None
                    t = entry.get("published_parsed")
                    if t:
                        try:
                            published_at = datetime(*t[:6])
                        except (TypeError, ValueError):
                            published_at = None

                    events.append(
                        {
                            "source": name,
                            "category": "news",
                            "title": title,
                            "summary": summary,
                            "url": link,
                            "published_at": published_at,
                            "content_hash": content_hash(name, title, link),
                        }
                    )
            except Exception:
                logger.exception("RSS feed %s (%s) failed", name, url)

    return await store_events(session, events)

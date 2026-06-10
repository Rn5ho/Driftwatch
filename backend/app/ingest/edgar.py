"""SEC EDGAR full-text search — crypto-relevant filings (the slow-news edge).

Two queries per run ("bitcoin", "digital assets"), well under EDGAR's 10 req/s
fair-access limit. A proper User-Agent (with contact email) is mandatory.
"""

import logging
from datetime import datetime, timedelta
from urllib.parse import quote

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.ingest.base import content_hash, store_events

logger = logging.getLogger(__name__)

EDGAR_FTS = "https://efts.sec.gov/LATEST/search-index"
QUERIES: list[str] = ['"bitcoin"', '"digital assets"']
FORMS = "8-K"
# Full-text search is relevance-ordered, not date-ordered — without a date
# window it returns years-old filings. We only want fresh, underread documents.
LOOKBACK_DAYS = 7


def _archive_url(hit_id: str, src: dict) -> str | None:
    """Build a sec.gov Archives URL from an _id like "accession:filename" and
    the filer CIK, when all the pieces are present."""
    try:
        accession, _, filename = hit_id.partition(":")
        ciks = src.get("ciks") or []
        cik = str(ciks[0]).lstrip("0") if ciks else ""
        if accession and filename and cik:
            return (
                "https://www.sec.gov/Archives/edgar/data/"
                f"{cik}/{accession.replace('-', '')}/{filename}"
            )
    except Exception:
        pass
    return None


def _hit_to_event(hit: dict, query: str) -> dict | None:
    """Defensively map one full-text-search hit to an Event dict."""
    hit_id = str(hit.get("_id") or "")
    if not hit_id:
        return None
    src: dict = hit.get("_source") or {}

    display_names = src.get("display_names") or []
    filer = str(display_names[0]) if display_names else "Unknown filer"
    form = str(src.get("file_type") or src.get("form") or "filing")
    file_date = str(src.get("file_date") or "")

    published_at: datetime | None = None
    if file_date:
        try:
            published_at = datetime.strptime(file_date[:10], "%Y-%m-%d")
        except ValueError:
            published_at = None

    url = _archive_url(hit_id, src) or f"{EDGAR_FTS}?q={quote(query)}&forms={FORMS}"

    return {
        "source": "sec_edgar",
        "category": "filing",
        "title": f"{form} — {filer}",
        "summary": f"SEC {form} filed {file_date or 'date unknown'} (matched {query})",
        "url": url,
        "published_at": published_at,
        "content_hash": content_hash("edgar", hit_id),
    }


async def ingest_edgar(session: AsyncSession) -> int:
    """Run the full-text queries, store new filings as Events. Returns inserted count."""
    headers = {"User-Agent": settings.edgar_user_agent}
    events: list[dict] = []
    cutoff = datetime.utcnow() - timedelta(days=LOOKBACK_DAYS)

    async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
        for query in QUERIES:
            try:
                resp = await client.get(
                    EDGAR_FTS,
                    params={
                        "q": query,
                        "forms": FORMS,
                        "dateRange": "custom",
                        "startdt": cutoff.strftime("%Y-%m-%d"),
                        "enddt": datetime.utcnow().strftime("%Y-%m-%d"),
                    },
                    headers=headers,
                )
                resp.raise_for_status()
                data = resp.json()
                hits = (data.get("hits") or {}).get("hits") or []
                for hit in hits:
                    try:
                        event = _hit_to_event(hit, query)
                        # Belt and suspenders: drop stale hits even if the
                        # server-side date filter is ignored.
                        if event is not None and (
                            event["published_at"] is None or event["published_at"] >= cutoff
                        ):
                            events.append(event)
                    except Exception:
                        logger.warning("Skipping malformed EDGAR hit", exc_info=True)
            except Exception:
                logger.exception("EDGAR query %r failed", query)

    # store_events also dedupes within the batch, so a filing matching both
    # queries is only inserted once.
    return await store_events(session, events)

"""Pipeline orchestration: events -> triage -> analysis -> escalation -> trade.

Implements steps 2-3 of the signal lifecycle (SPEC section 3) as a model
cascade (SPEC section 4b). The LLMs only forecast probabilities; sizing and
vetoes are deterministic code.

Transaction discipline (review-driven): SQLite allows one writer, so NO DB
transaction is ever held across LLM or HTTP calls. Each batch does a short
read transaction (candidates + market rows), then per event: all LLM calls
with no session open, then live price fetches, then one short write
transaction. LLM failures leave the event unprocessed (retried next cycle,
up to MAX_ATTEMPTS) and abort the batch — an API outage must not burn the
queue. Every decision is written to the activity ledger with its reason, and
every LLM call is ledgered with real token usage and estimated cost.
"""

import asyncio
import logging
import os
import random
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.activity import log_activity
from app.analysis.analyst import AnalystCall, analyze_event, triage_event
from app.analysis.costs import estimate_cost_usd
from app.analysis.regime import classify_regime
from app.config import settings
from app.db import session_scope
from app.ingest.prices import compute_price_context, fetch_price
from app.models import Event, Forecast, LlmCall, MarketSnapshot, OddsSnapshot
from app.schemas import ForecastOutput
from app.trading.paper import compute_equity, open_trade
from app.trading.sizing import funding_veto, kelly_size

logger = logging.getLogger(__name__)

# Concurrent invocations (manual trigger during a scheduled run) would select
# the same unprocessed events and run the whole cascade twice.
_analyze_lock = asyncio.Lock()

MAX_ATTEMPTS = 3  # failed-LLM retries per event before giving up (poison guard)


def should_escalate(result: ForecastOutput) -> bool:
    """Escalate to the strong model when paper capital might move (forecast is
    within escalation_margin of the trade threshold) or the category is
    high-stakes. Opus spend scales with decisions, not event volume."""
    if (
        result.direction != "none"
        and result.probability >= settings.min_probability - settings.escalation_margin
    ):
        return True
    return result.category in settings.escalation_categories


def _event_payload(event: Event) -> dict[str, Any]:
    return {
        "source": event.source,
        "category": event.category,
        "title": event.title,
        "summary": event.summary,
        "url": event.url,
        "published_at": event.published_at.isoformat() if event.published_at else None,
        "fetched_at": event.fetched_at.isoformat() if event.fetched_at else None,
    }


def _regime_for(result: ForecastOutput, market_context: dict[str, Any]) -> str:
    info: dict[str, Any] = market_context["assets"].get(result.asset, {})
    return classify_regime(info.get("ret_7d"), info.get("vol_24h"))


def _forecast_row(
    event_id: int,
    result: ForecastOutput,
    market_context: dict[str, Any],
    model: str,
    stage: str,
    shadow: bool,
    price: float | None,
) -> Forecast:
    return Forecast(
        event_id=event_id,
        asset=result.asset,
        category=result.category,
        direction=result.direction,
        probability=result.probability,
        market_prior=None,  # Polymarket prior matching is phase 1
        horizon_hours=result.horizon_hours,
        thesis=result.thesis,
        what_is_priced_in=result.what_is_priced_in,
        key_risks=result.key_risks,
        model=model,
        stage=stage,
        shadow=shadow,
        regime=_regime_for(result, market_context),
        price_at_forecast=price,
    )


def _store_calls(
    session: AsyncSession, calls: list[tuple[str, AnalystCall]], event_id: int
) -> None:
    for role, call in calls:
        session.add(
            LlmCall(
                model=call.model,
                role=role,
                event_id=event_id,
                input_tokens=call.input_tokens,
                output_tokens=call.output_tokens,
                cost_usd=estimate_cost_usd(call.model, call.input_tokens, call.output_tokens),
                ok=call.ok,
            )
        )


async def _read_market_rows(session: AsyncSession) -> tuple[dict, list]:
    """DB reads only — the network half of market context happens outside any
    transaction."""
    snapshots: dict[str, dict[str, float | None]] = {}
    for asset in settings.assets:
        snap = (
            await session.execute(
                select(MarketSnapshot)
                .where(MarketSnapshot.asset == asset)
                .order_by(MarketSnapshot.ts.desc())
                .limit(1)
            )
        ).scalars().first()
        if snap is not None:
            snapshots[asset] = {
                "price": snap.price,
                "funding_rate": snap.funding_rate,
                "open_interest": snap.open_interest,
            }

    odds_rows = (
        await session.execute(select(OddsSnapshot).order_by(OddsSnapshot.ts.desc()).limit(200))
    ).scalars().all()
    seen_slugs: set[str] = set()
    odds: list[dict[str, Any]] = []
    for row in odds_rows:
        if row.market_slug in seen_slugs:
            continue
        seen_slugs.add(row.market_slug)
        odds.append(
            {
                "market_slug": row.market_slug,
                "question": row.question,
                "yes_price": row.yes_price,
            }
        )
        if len(odds) >= 10:
            break
    return snapshots, odds


async def _live_prices(
    assets: set[str], market_context: dict[str, Any]
) -> dict[str, float | None]:
    """Live price per asset at decision time; batch snapshot only as fallback.
    A fill stamped with a stale price books pre-decision movement as PnL."""
    prices: dict[str, float | None] = {}
    for asset in assets:
        try:
            prices[asset] = await fetch_price(f"{asset}USDT")
        except Exception:
            logger.warning("live price fetch failed for %s — falling back to batch snapshot", asset)
            info: dict[str, Any] = market_context["assets"].get(asset, {})
            prices[asset] = info.get("price")
    return prices


async def analyze_pending(limit: int = 10) -> int:
    """Run up to `limit` unprocessed events through the cascade. Returns the
    number of canonical (non-shadow) forecasts created. Never raises to the
    scheduler; concurrent invocations are rejected."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        logger.warning("ANTHROPIC_API_KEY not set — skipping analysis, leaving events unprocessed")
        return 0
    if _analyze_lock.locked():
        logger.info("analysis already running — skipping concurrent invocation")
        return 0
    async with _analyze_lock:
        try:
            return await _analyze_pending_locked(limit)
        except Exception:
            logger.exception("analyze_pending failed")
            return 0


async def _analyze_pending_locked(limit: int) -> int:
    # Phase 1 — short read transaction: candidates + market rows.
    async with session_scope() as session:
        events = (
            await session.execute(
                select(Event)
                .where(Event.processed.is_(False))
                .order_by(Event.fetched_at.asc())
                .limit(limit)
            )
        ).scalars().all()
        candidates = [(e.id, e.attempts, _event_payload(e)) for e in events]
        snapshots, odds = await _read_market_rows(session)
    if not candidates:
        return 0

    # Phase 2 — network, no transaction: price-action context per asset.
    assets_ctx: dict[str, dict[str, float | None]] = {}
    for asset in settings.assets:
        info: dict[str, float | None] = dict(await compute_price_context(f"{asset}USDT"))
        info.update(snapshots.get(asset, {}))
        assets_ctx[asset] = info
    market_context: dict[str, Any] = {"assets": assets_ctx, "polymarket_odds": odds}

    created = 0
    for event_id, attempts, payload in candidates:
        n, abort = await _process_event(event_id, attempts, payload, market_context)
        created += n
        if abort:
            logger.warning(
                "aborting analyze batch after LLM failure on event id=%s — retried next cycle",
                event_id,
            )
            break
    return created


async def _handle_llm_failure(
    event_id: int, attempts: int, calls: list[tuple[str, AnalystCall]], role: str
) -> bool:
    """Record the failure; leave the event unprocessed for retry unless it has
    exhausted MAX_ATTEMPTS. Returns True when the batch should abort (failure
    is likely systemic: outage or bad key)."""
    async with session_scope() as session:
        event = await session.get(Event, event_id)
        if event is None:
            return True
        _store_calls(session, calls, event_id)
        event.attempts = attempts + 1
        if event.attempts >= MAX_ATTEMPTS:
            event.processed = True
            log_activity(
                session, "error",
                f"{role} failed {event.attempts}x — giving up on this event",
                event_id=event_id,
            )
            return False  # poison event removed from the queue; batch can continue
        log_activity(
            session, "error",
            f"{role} call failed (attempt {event.attempts}/{MAX_ATTEMPTS}) — will retry",
            event_id=event_id,
        )
    return True


async def _process_event(
    event_id: int, attempts: int, payload: dict[str, Any], market_context: dict[str, Any]
) -> tuple[int, bool]:
    """Full cascade for one event. Returns (canonical forecasts created,
    abort batch?). No DB session is open during LLM/HTTP work."""
    calls: list[tuple[str, AnalystCall]] = []

    # --- Stage 1: triage (cheap model) ---
    tcall = await triage_event(payload)
    calls.append(("triage", tcall))
    if tcall.output is None:
        return 0, await _handle_llm_failure(event_id, attempts, calls, "triage")
    triage = tcall.output
    if not triage.is_market_relevant:
        async with session_scope() as session:
            event = await session.get(Event, event_id)
            event.processed = True
            event.triage_relevant = False
            _store_calls(session, calls, event_id)
            log_activity(session, "triage_reject", triage.reason, event_id=event_id)
        return 0, False

    # --- Stage 2: analysis (default model) ---
    acall = await analyze_event(payload, market_context)
    calls.append(("analysis", acall))
    if acall.output is None:
        return 0, await _handle_llm_failure(event_id, attempts, calls, "analysis")
    result: ForecastOutput = acall.output
    if not result.is_market_relevant:
        async with session_scope() as session:
            event = await session.get(Event, event_id)
            event.processed = True
            event.triage_relevant = True
            _store_calls(session, calls, event_id)
            log_activity(
                session, "analyst_reject",
                f"analyst judged not market-relevant ({result.category})",
                event_id=event_id,
            )
        return 0, False

    canonical = result
    canonical_model = settings.analyst_model
    stage = "analysis"
    paired_shadow: ForecastOutput | None = None
    ensemble_veto = False

    # --- Stage 3: escalation (strong model) ---
    if should_escalate(result):
        ecall = await analyze_event(payload, market_context, model=settings.escalation_model)
        calls.append(("escalation", ecall))
        if ecall.output is not None:
            escalated: ForecastOutput = ecall.output
            paired_shadow = result  # every escalation produces free paired data
            if (
                escalated.direction != result.direction
                and result.direction != "none"
                and escalated.direction != "none"
            ):
                ensemble_veto = True
            canonical = escalated
            canonical_model = settings.escalation_model
            stage = "escalation"

    # --- Shadow sampling: paired model-quality measurement ---
    sampled: list[tuple[str, ForecastOutput]] = []
    if random.random() < settings.shadow_rate:
        for shadow_model in settings.shadow_models:
            if shadow_model == canonical_model:
                continue
            scall = await analyze_event(payload, market_context, model=shadow_model)
            calls.append(("shadow", scall))
            if scall.output is not None:
                sampled.append((shadow_model, scall.output))

    # --- Price phase: live fetch AFTER all LLM latency, per distinct asset ---
    outputs: list[ForecastOutput] = [canonical] + ([paired_shadow] if paired_shadow else []) \
        + [output for _, output in sampled]
    assets_needed = {o.asset for o in outputs if o.asset != "NONE"}
    prices = await _live_prices(assets_needed, market_context)

    # --- Write phase: one short transaction for the whole event ---
    async with session_scope() as session:
        event = await session.get(Event, event_id)
        event.processed = True
        event.triage_relevant = True
        _store_calls(session, calls, event_id)

        if paired_shadow is not None:
            session.add(
                _forecast_row(
                    event_id, paired_shadow, market_context,
                    model=settings.analyst_model, stage="analysis", shadow=True,
                    price=prices.get(paired_shadow.asset),
                )
            )
        forecast = _forecast_row(
            event_id, canonical, market_context,
            model=canonical_model, stage=stage, shadow=False,
            price=prices.get(canonical.asset),
        )
        session.add(forecast)
        for shadow_model, output in sampled:
            session.add(
                _forecast_row(
                    event_id, output, market_context,
                    model=shadow_model, stage="shadow", shadow=True,
                    price=prices.get(output.asset),
                )
            )
        await session.flush()  # assign forecast.id before activities/trade

        log_activity(
            session, "forecast",
            f"{canonical.asset} {canonical.direction} p={canonical.probability:.2f} "
            f"{canonical.horizon_hours}h [{stage}] — {canonical.thesis[:180]}",
            event_id=event_id, forecast_id=forecast.id,
        )
        if stage == "escalation":
            log_activity(
                session, "escalation",
                ("models DISAGREE on direction — trade vetoed"
                 if ensemble_veto
                 else f"{settings.escalation_model} confirms {canonical.direction} "
                      f"p={canonical.probability:.2f}"),
                event_id=event_id, forecast_id=forecast.id,
            )

        # --- Trade filters (SPEC section 3) — all deterministic ---
        skip_reason: str | None = None
        if ensemble_veto:
            skip_reason = "ensemble disagreement between analysis and escalation models"
        elif not canonical.is_market_relevant or canonical.direction == "none" or canonical.asset == "NONE":
            skip_reason = "no tradeable direction"
        elif canonical.probability < settings.min_probability:
            skip_reason = (
                f"p={canonical.probability:.2f} below min_probability {settings.min_probability:.2f}"
            )
        else:
            funding = market_context["assets"].get(canonical.asset, {}).get("funding_rate")
            if funding_veto(canonical.direction, funding, settings.funding_veto_abs):
                skip_reason = f"funding veto (crowded {canonical.direction}, funding={funding})"

        if skip_reason is None:
            try:
                price = forecast.price_at_forecast
                equity = await compute_equity(session)
                notional = kelly_size(
                    canonical.probability, equity,
                    settings.kelly_fraction, settings.max_position_frac,
                )
                if notional <= 0:
                    skip_reason = "kelly size is zero"
                elif price is None:
                    skip_reason = "no reference price available"
                else:
                    trade = await open_trade(session, forecast, price, notional)
                    log_activity(
                        session, "trade_open",
                        f"{trade.side} {trade.asset} notional={trade.notional:.2f} "
                        f"@ {trade.entry_price:.4f} (equity={equity:.2f})",
                        event_id=event_id, forecast_id=forecast.id, trade_id=trade.id,
                    )
            except Exception:
                logger.exception("failed to open trade for forecast id=%s", forecast.id)
                skip_reason = "trade-open error (see logs)"

        if skip_reason is not None:
            log_activity(
                session, "trade_skip", skip_reason,
                event_id=event_id, forecast_id=forecast.id,
            )
    return 1, False

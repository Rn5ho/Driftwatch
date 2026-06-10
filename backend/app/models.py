from datetime import datetime

from sqlalchemy import ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Event(Base):
    """One ingested news item / filing / post. Timestamps are honest:
    published_at is the source's claim, fetched_at is our clock — the gap is
    our real latency and is part of the dataset."""

    __tablename__ = "events"

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(index=True)
    category: Mapped[str] = mapped_column(default="news")
    title: Mapped[str] = mapped_column(Text)
    summary: Mapped[str] = mapped_column(Text, default="")
    url: Mapped[str] = mapped_column(default="")
    published_at: Mapped[datetime | None] = mapped_column(default=None)
    fetched_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    content_hash: Mapped[str] = mapped_column(unique=True, index=True)
    processed: Mapped[bool] = mapped_column(default=False, index=True)
    triage_relevant: Mapped[bool | None] = mapped_column(default=None)
    attempts: Mapped[int] = mapped_column(default=0)  # failed LLM attempts; poison guard


class MarketSnapshot(Base):
    __tablename__ = "market_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    asset: Mapped[str] = mapped_column(index=True)  # "BTC", "ETH", ...
    ts: Mapped[datetime] = mapped_column(default=datetime.utcnow, index=True)
    price: Mapped[float]
    funding_rate: Mapped[float | None] = mapped_column(default=None)
    open_interest: Mapped[float | None] = mapped_column(default=None)


class OddsSnapshot(Base):
    """Polymarket odds — our measurement instrument for what's priced in."""

    __tablename__ = "odds_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    market_slug: Mapped[str] = mapped_column(index=True)
    question: Mapped[str] = mapped_column(Text)
    ts: Mapped[datetime] = mapped_column(default=datetime.utcnow, index=True)
    yes_price: Mapped[float]            # implied probability, 0..1
    volume: Mapped[float | None] = mapped_column(default=None)


class Forecast(Base):
    """A falsifiable, timestamped prediction. The ledger of these — resolved
    against outcomes with Brier scores — is the system's learning loop."""

    __tablename__ = "forecasts"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int | None] = mapped_column(ForeignKey("events.id"), default=None)
    asset: Mapped[str]                  # "BTC" | "ETH" | "SOL" | "NONE"
    category: Mapped[str] = mapped_column(index=True)
    direction: Mapped[str]              # "long" | "short" | "none"
    probability: Mapped[float]          # LLM's calibrated P(thesis true at horizon)
    market_prior: Mapped[float | None] = mapped_column(default=None)
    horizon_hours: Mapped[int] = mapped_column(default=24)
    thesis: Mapped[str] = mapped_column(Text, default="")
    what_is_priced_in: Mapped[str] = mapped_column(Text, default="")
    key_risks: Mapped[str] = mapped_column(Text, default="")
    model: Mapped[str] = mapped_column(default="")
    stage: Mapped[str] = mapped_column(default="analysis")  # "analysis" | "escalation" | "shadow"
    shadow: Mapped[bool] = mapped_column(default=False, index=True)  # never traded; model-comparison data
    regime: Mapped[str] = mapped_column(default="")  # market regime at creation, e.g. "up/high_vol"
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow, index=True)
    price_at_forecast: Mapped[float | None] = mapped_column(default=None)

    # Resolution
    resolved_at: Mapped[datetime | None] = mapped_column(default=None)
    price_at_resolution: Mapped[float | None] = mapped_column(default=None)
    outcome: Mapped[int | None] = mapped_column(default=None)  # 1 thesis true, 0 false
    brier: Mapped[float | None] = mapped_column(default=None)


class Trade(Base):
    __tablename__ = "trades"

    id: Mapped[int] = mapped_column(primary_key=True)
    forecast_id: Mapped[int] = mapped_column(ForeignKey("forecasts.id"))
    asset: Mapped[str]
    side: Mapped[str]                   # "long" | "short"
    notional: Mapped[float]
    entry_price: Mapped[float]
    entry_ts: Mapped[datetime] = mapped_column(default=datetime.utcnow, index=True)
    exit_price: Mapped[float | None] = mapped_column(default=None)
    exit_ts: Mapped[datetime | None] = mapped_column(default=None)
    fees: Mapped[float] = mapped_column(default=0.0)
    pnl: Mapped[float | None] = mapped_column(default=None)
    status: Mapped[str] = mapped_column(default="open", index=True)  # "open" | "closed"


class LlmCall(Base):
    """One LLM API call — real token usage and estimated cost, per role."""

    __tablename__ = "llm_calls"

    id: Mapped[int] = mapped_column(primary_key=True)
    ts: Mapped[datetime] = mapped_column(default=datetime.utcnow, index=True)
    model: Mapped[str] = mapped_column(index=True)
    role: Mapped[str]  # "triage" | "analysis" | "escalation" | "shadow"
    event_id: Mapped[int | None] = mapped_column(ForeignKey("events.id"), default=None)
    input_tokens: Mapped[int] = mapped_column(default=0)
    output_tokens: Mapped[int] = mapped_column(default=0)
    cost_usd: Mapped[float] = mapped_column(default=0.0)
    ok: Mapped[bool] = mapped_column(default=True)


class Activity(Base):
    """The system narrating its own decisions — every triage verdict, forecast,
    trade, skip (with reason), resolution, and error. The dashboard's feed."""

    __tablename__ = "activity"

    id: Mapped[int] = mapped_column(primary_key=True)
    ts: Mapped[datetime] = mapped_column(default=datetime.utcnow, index=True)
    kind: Mapped[str] = mapped_column(index=True)
    message: Mapped[str] = mapped_column(Text)
    event_id: Mapped[int | None] = mapped_column(default=None)
    forecast_id: Mapped[int | None] = mapped_column(default=None)
    trade_id: Mapped[int | None] = mapped_column(default=None)


class Portfolio(Base):
    """Singleton row (id=1)."""

    __tablename__ = "portfolio"

    id: Mapped[int] = mapped_column(primary_key=True)
    starting_cash: Mapped[float]
    cash: Mapped[float]
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)

"""Calibration: Brier scoring and per-category calibration report.

The forecast ledger, resolved against outcomes, is the system's learning loop.
Volumes are small, so aggregation is done in Python rather than SQL.
"""

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Forecast

logger = logging.getLogger(__name__)


def brier(probability: float, outcome: int) -> float:
    """Brier score for a single resolved forecast: (p - outcome)^2."""
    return (probability - outcome) ** 2


async def calibration_report(session: AsyncSession) -> list[dict]:
    """Per-category calibration over resolved forecasts (outcome is not None).

    Returns one row per category plus an aggregate "ALL" row, sorted by n
    descending: {category, n, mean_brier, hit_rate, mean_probability}.
    Floats are rounded to 4 decimals. Shadow forecasts are excluded — this
    report measures the trading system; model_comparison measures the models.
    """
    result = await session.execute(
        select(Forecast).where(Forecast.outcome.is_not(None), Forecast.shadow.is_(False))
    )
    forecasts = list(result.scalars().all())

    groups: dict[str, list[Forecast]] = {}
    for forecast in forecasts:
        groups.setdefault(forecast.category, []).append(forecast)

    def _row(category: str, items: list[Forecast]) -> dict:
        n = len(items)
        briers = [
            f.brier if f.brier is not None else brier(f.probability, f.outcome)  # type: ignore[arg-type]
            for f in items
        ]
        return {
            "category": category,
            "n": n,
            "mean_brier": round(sum(briers) / n, 4),
            "hit_rate": round(sum(1 for f in items if f.outcome == 1) / n, 4),
            "mean_probability": round(sum(f.probability for f in items) / n, 4),
        }

    rows: list[dict] = [_row(category, items) for category, items in groups.items()]
    if forecasts:
        rows.append(_row("ALL", forecasts))
    rows.sort(key=lambda r: r["n"], reverse=True)
    return rows


async def model_comparison(session: AsyncSession) -> list[dict]:
    """Per-model Brier comparison over the PAIRED subset only: events that
    have resolved forecasts from at least two distinct models.

    Pooling all resolved forecasts would confound model skill with event
    selection — Opus rows are dominated by escalations, which are selected
    precisely because they are near-tradeable or high-stakes. Restricting to
    multi-model events keeps the populations comparable: same events,
    different models, identical scoring. Returns {model, n, mean_brier,
    hit_rate, mean_probability} sorted by n descending.
    """
    result = await session.execute(
        select(Forecast).where(
            Forecast.outcome.is_not(None), Forecast.event_id.is_not(None)
        )
    )
    forecasts = list(result.scalars().all())

    by_event: dict[int, list[Forecast]] = {}
    for forecast in forecasts:
        by_event.setdefault(forecast.event_id, []).append(forecast)  # type: ignore[arg-type]
    paired = [
        forecast
        for items in by_event.values()
        if len({item.model for item in items}) >= 2
        for forecast in items
    ]

    groups: dict[str, list[Forecast]] = {}
    for forecast in paired:
        groups.setdefault(forecast.model or "unknown", []).append(forecast)

    rows: list[dict] = []
    for model, items in groups.items():
        n = len(items)
        briers = [
            f.brier if f.brier is not None else brier(f.probability, f.outcome)  # type: ignore[arg-type]
            for f in items
        ]
        rows.append(
            {
                "model": model,
                "n": n,
                "mean_brier": round(sum(briers) / n, 4),
                "hit_rate": round(sum(1 for f in items if f.outcome == 1) / n, 4),
                "mean_probability": round(sum(f.probability for f in items) / n, 4),
            }
        )
    rows.sort(key=lambda r: r["n"], reverse=True)
    return rows

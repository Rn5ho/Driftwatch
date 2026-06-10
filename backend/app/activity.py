"""Helper for the activity ledger — the system narrating its decisions."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Activity


def log_activity(
    session: AsyncSession,
    kind: str,
    message: str,
    event_id: int | None = None,
    forecast_id: int | None = None,
    trade_id: int | None = None,
) -> None:
    session.add(
        Activity(
            kind=kind,
            message=message,
            event_id=event_id,
            forecast_id=forecast_id,
            trade_id=trade_id,
        )
    )

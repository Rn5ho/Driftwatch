"""Runtime ledger audit: invariants that must always hold.

We cannot prove the absence of bugs; we can make violations visible. These
checks run on demand (GET /api/ops/audit, polled by the dashboard) so ledger
corruption becomes a red light, not a discovery weeks later.
"""

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Forecast, Portfolio, Trade

logger = logging.getLogger(__name__)

_CENT = 0.011  # money comparisons: rounding happens at cents
_EPS = 1e-6


def _check(name: str, ok: bool, detail: str) -> dict:
    return {"check": name, "ok": ok, "detail": detail}


async def run_audit(session: AsyncSession) -> list[dict]:
    checks: list[dict] = []

    portfolio = (
        await session.execute(select(Portfolio).where(Portfolio.id == 1))
    ).scalar_one_or_none()
    trades = list((await session.execute(select(Trade))).scalars().all())
    forecasts = list((await session.execute(select(Forecast))).scalars().all())
    forecast_by_id = {f.id: f for f in forecasts}
    closed = [t for t in trades if t.status == "closed"]
    open_trades = [t for t in trades if t.status == "open"]

    # 1. Cash equation: cash never moves except by realized PnL at close.
    if portfolio is None:
        checks.append(_check("cash_equation", True, "no portfolio row yet"))
    else:
        expected = portfolio.starting_cash + sum(t.pnl or 0.0 for t in closed)
        drift = portfolio.cash - expected
        checks.append(
            _check(
                "cash_equation",
                abs(drift) < _CENT * max(1, len(closed)),
                f"cash={portfolio.cash:.2f} expected={expected:.2f} drift={drift:+.4f}",
            )
        )

    # 2. Closed-trade math: pnl == sign*return*notional - fees (to the cent).
    bad = []
    for t in closed:
        if t.exit_price is None or t.pnl is None:
            bad.append(f"trade {t.id}: closed but missing exit_price/pnl")
            continue
        sign = 1.0 if t.side == "long" else -1.0
        expected_pnl = sign * (t.exit_price - t.entry_price) / t.entry_price * t.notional - t.fees
        if abs(t.pnl - expected_pnl) > 0.02:
            bad.append(f"trade {t.id}: pnl={t.pnl} expected={expected_pnl:.2f}")
    checks.append(_check("closed_trade_math", not bad, "; ".join(bad) or f"{len(closed)} closed trades consistent"))

    # 3. Trade shape: fees/notional sane; open trades have no exit fields.
    bad = []
    for t in trades:
        if t.fees < 0 or t.notional <= 0:
            bad.append(f"trade {t.id}: fees={t.fees} notional={t.notional}")
        if t.status == "open" and (t.exit_price is not None or t.exit_ts is not None or t.pnl is not None):
            bad.append(f"trade {t.id}: open but has exit fields")
    checks.append(_check("trade_shape", not bad, "; ".join(bad) or f"{len(trades)} trades well-formed"))

    # 4. Trades reference a canonical (non-shadow) forecast with matching side.
    bad = []
    for t in trades:
        f = forecast_by_id.get(t.forecast_id)
        if f is None:
            bad.append(f"trade {t.id}: missing forecast {t.forecast_id}")
        elif f.shadow:
            bad.append(f"trade {t.id}: opened on SHADOW forecast {f.id}")
        elif f.direction != t.side:
            bad.append(f"trade {t.id}: side={t.side} but forecast direction={f.direction}")
    checks.append(_check("trade_forecast_link", not bad, "; ".join(bad) or "all trades linked to canonical forecasts"))

    # 5. At most one canonical forecast per event (escalation replaces, never duplicates).
    canon_events: dict[int, int] = {}
    for f in forecasts:
        if not f.shadow and f.event_id is not None:
            canon_events[f.event_id] = canon_events.get(f.event_id, 0) + 1
    dups = {k: v for k, v in canon_events.items() if v > 1}
    checks.append(
        _check(
            "single_canonical_per_event",
            not dups,
            f"duplicate canonical forecasts for events: {dups}" if dups else f"{len(canon_events)} events, all single-canonical",
        )
    )

    # 6. Resolution integrity: brier == (p-outcome)^2, outcome binary, price recorded.
    bad = []
    for f in forecasts:
        if f.outcome is None:
            continue
        if f.outcome not in (0, 1):
            bad.append(f"forecast {f.id}: outcome={f.outcome}")
        elif f.brier is None or abs(f.brier - (f.probability - f.outcome) ** 2) > _EPS:
            bad.append(f"forecast {f.id}: brier={f.brier}")
        elif f.price_at_resolution is None or f.resolved_at is None:
            bad.append(f"forecast {f.id}: resolved without price/timestamp")
    n_resolved = sum(1 for f in forecasts if f.outcome is not None)
    checks.append(_check("resolution_integrity", not bad, "; ".join(bad) or f"{n_resolved} resolutions consistent"))

    # 7. Probability bounds.
    bad = [f"forecast {f.id}: p={f.probability}" for f in forecasts if not 0.0 <= f.probability <= 1.0]
    checks.append(_check("probability_bounds", not bad, "; ".join(bad) or f"{len(forecasts)} forecasts in bounds"))

    return checks

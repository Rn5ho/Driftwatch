"""Deterministic position sizing and risk vetoes.

The LLM forecasts probabilities only; everything in this module is pure,
deterministic code (SPEC section 4). No I/O.
"""


def kelly_size(probability: float, equity: float, kelly_fraction: float, max_frac: float) -> float:
    """Fractional-Kelly notional for an even-odds binary bet.

    raw_kelly = 2p - 1; returns 0.0 for p <= 0.5 (no edge). The applied
    fraction is capped at ``max_frac`` of equity. Result rounded to cents.
    """
    raw = 2.0 * probability - 1.0
    if raw <= 0:
        return 0.0
    frac = min(kelly_fraction * raw, max_frac)
    return round(frac * equity, 2)


def funding_veto(direction: str, funding_rate: float | None, threshold: float) -> bool:
    """True = BLOCKED: entering in the direction of crowded positioning.

    Longs are blocked when funding > +threshold (crowded long); shorts are
    blocked when funding < -threshold (crowded short). Unknown funding never
    blocks.
    """
    if funding_rate is None:
        return False
    if direction == "long" and funding_rate > threshold:
        return True
    if direction == "short" and funding_rate < -threshold:
        return True
    return False

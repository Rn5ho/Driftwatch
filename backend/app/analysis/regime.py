"""Market regime classification (v0 heuristic).

Each forecast is stamped with the regime at creation so the calibration
ledger can eventually answer regime-conditional questions ("fading hack news
works in ranging markets, fails in crashes"). Thresholds are deliberately
simple and documented; refine once the ledger has data to validate against.
"""

TREND_THRESHOLD = 0.05   # |7d return| above this is a trend
HIGH_VOL_THRESHOLD = 0.04  # daily-ized realized vol above this is high-vol


def classify_regime(ret_7d: float | None, vol_24h: float | None) -> str:
    """"up"/"down"/"flat" 7d trend bucket + "high_vol"/"low_vol" bucket.

    Returns "" when inputs are unavailable — an honest unknown, not a guess.
    """
    if ret_7d is None or vol_24h is None:
        return ""
    if ret_7d > TREND_THRESHOLD:
        trend = "up"
    elif ret_7d < -TREND_THRESHOLD:
        trend = "down"
    else:
        trend = "flat"
    vol = "high_vol" if vol_24h > HIGH_VOL_THRESHOLD else "low_vol"
    return f"{trend}/{vol}"

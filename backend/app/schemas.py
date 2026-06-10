from typing import Literal

from pydantic import BaseModel, Field

Category = Literal[
    "macro",
    "regulation",
    "etf_flow",
    "exchange",
    "hack_security",
    "token_unlock",
    "adoption",
    "ai_tech",
    "geopolitics",
    "market_structure",
    "filing",
    "governance",
    "noise",
    "other",
]

Direction = Literal["long", "short", "none"]
Asset = Literal["BTC", "ETH", "SOL", "NONE"]


class TriageOutput(BaseModel):
    """Stage-1 relevance gate (cheap model). Most news must die here."""

    is_market_relevant: bool = Field(
        description="True only if this event could plausibly move BTC, ETH, or SOL over a 12-72h horizon. Routine coverage, price recaps, opinion pieces, re-reported stories, minor partnerships: False. When in doubt: False."
    )
    reason: str = Field(description="One short sentence justifying the verdict.")


class ForecastOutput(BaseModel):
    """Structured output contract for the analyst LLM call.

    The model forecasts; it NEVER sizes. Probability must be an honest,
    calibrated estimate — it is Brier-scored against the realized outcome.
    """

    is_market_relevant: bool = Field(
        description="False for routine/noise items that should not move crypto prices over the stated horizon. Most news is noise."
    )
    category: Category = Field(description="Event category for calibration bucketing.")
    asset: Asset = Field(description="The single asset this thesis applies to, or NONE.")
    direction: Direction = Field(
        description="Directional thesis for the asset over the horizon. 'none' if relevant but no tradable direction."
    )
    probability: float = Field(
        ge=0.0,
        le=1.0,
        description="Calibrated probability that the directional thesis resolves true at the horizon (signed return matches direction). Use the full 0-1 range honestly.",
    )
    what_is_priced_in: str = Field(
        description="What the market already expects/knows about this. The trade is the gap between outcome and expectation, not the raw news."
    )
    thesis: str = Field(description="The falsifiable thesis, 1-3 sentences, including second-order effects considered.")
    key_risks: str = Field(description="What would make this forecast wrong.")
    horizon_hours: int = Field(
        ge=1, le=168, description="Hours until the thesis should have played out. Prefer 12-72h; we trade drift, not jumps."
    )

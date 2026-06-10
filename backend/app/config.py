from pathlib import Path

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

# Load backend/.env into the process environment so the Anthropic SDK
# (which reads ANTHROPIC_API_KEY itself) sees it too.
load_dotenv(Path(__file__).resolve().parent.parent / ".env")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DRIFTWATCH_", extra="ignore")

    # Model cascade: cost scales with decisions, not volume. Haiku rejects the
    # ~90% noise, Sonnet analyzes survivors, Opus re-analyzes only when paper
    # capital is about to move or the category is high-stakes.
    triage_model: str = "claude-haiku-4-5"
    analyst_model: str = "claude-sonnet-4-6"
    escalation_model: str = "claude-opus-4-8"
    escalation_margin: float = 0.05    # escalate when p >= min_probability - margin
    escalation_categories: list[str] = ["macro", "regulation", "hack_security", "etf_flow"]
    # Shadow scoring: fraction of analyzed events also scored by the other
    # models (never traded, Brier-scored identically) — the paired measurement
    # that answers "is the cheap model costing us alpha?".
    shadow_rate: float = 0.15
    shadow_models: list[str] = ["claude-opus-4-8", "claude-haiku-4-5"]

    db_url: str = "sqlite+aiosqlite:///./driftwatch.db"

    # Portfolio / risk — sizing is deterministic code, never the LLM.
    starting_cash: float = 10_000.0
    kelly_fraction: float = 0.25       # quarter-Kelly
    max_position_frac: float = 0.10    # cap per trade as fraction of equity
    fee_bps: float = 10.0              # round-trip cost model (fee + spread + slippage)
    min_probability: float = 0.60
    min_edge_to_trade: float = 0.05    # required edge vs market-implied prior, when one exists
    funding_veto_abs: float = 0.0008   # |8h funding| above this blocks crowded-side entries
    macro_no_trade_minutes: int = 15

    # Poll intervals (seconds)
    rss_poll_seconds: int = 300
    market_poll_seconds: int = 120
    polymarket_poll_seconds: int = 600
    edgar_poll_seconds: int = 3600
    analyze_poll_seconds: int = 180
    resolver_poll_seconds: int = 300

    assets: list[str] = ["BTC", "ETH", "SOL"]

    # Sent on SEC EDGAR requests (required by their fair-access policy).
    edgar_user_agent: str = "DriftWatch research matic.pp91@gmail.com"


settings = Settings()

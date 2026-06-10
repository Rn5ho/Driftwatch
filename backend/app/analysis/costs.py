"""LLM cost estimation from real token usage (prices per million tokens)."""

PRICES_PER_MTOK: dict[str, tuple[float, float]] = {
    # model prefix: (input $/MTok, output $/MTok)
    "claude-opus-4-8": (5.0, 25.0),
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-haiku-4-5": (1.0, 5.0),
}


def estimate_cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    """Estimated cost of one call. Unknown models cost 0 (and should be added
    to the table above)."""
    for prefix, (price_in, price_out) in PRICES_PER_MTOK.items():
        if model.startswith(prefix):
            return round((input_tokens * price_in + output_tokens * price_out) / 1_000_000, 6)
    return 0.0

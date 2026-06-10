"""Pure-function tests for deterministic sizing and the funding veto."""

import pytest

from app.trading.sizing import funding_veto, kelly_size


class TestKellySize:
    def test_zero_at_coin_flip(self) -> None:
        assert kelly_size(0.5, 10_000.0, 0.25, 0.10) == 0.0

    def test_zero_below_half(self) -> None:
        assert kelly_size(0.3, 10_000.0, 0.25, 0.10) == 0.0
        assert kelly_size(0.0, 10_000.0, 0.25, 0.10) == 0.0

    def test_quarter_kelly_math(self) -> None:
        # p=0.7 -> raw 0.4 -> quarter-Kelly fraction 0.1, exactly at the
        # 0.10 cap -> 10% of 10000 = 1000.
        assert kelly_size(0.7, 10_000.0, 0.25, 0.10) == 1000.0

    def test_cap_binds_at_high_probability(self) -> None:
        # p=0.99 -> raw 0.98 -> 0.245 uncapped, capped to 0.10 -> 1000.
        assert kelly_size(0.99, 10_000.0, 0.25, 0.10) == 1000.0

    def test_below_cap_scales_with_probability(self) -> None:
        # p=0.6 -> raw 0.2 -> 0.05 fraction -> 500 on 10000.
        assert kelly_size(0.6, 10_000.0, 0.25, 0.10) == 500.0

    def test_rounds_to_cents(self) -> None:
        # p=0.61 -> raw 0.22 -> 0.055 fraction on 1234.56 = 67.9008 -> 67.90
        assert kelly_size(0.61, 1234.56, 0.25, 0.10) == 67.9


class TestFundingVeto:
    THRESHOLD = 0.0008

    @pytest.mark.parametrize(
        ("direction", "funding_rate", "blocked"),
        [
            # Long blocked only when funding above +threshold (crowded long).
            ("long", 0.001, True),
            ("long", 0.0008, False),  # strict inequality: at threshold passes
            ("long", 0.0005, False),
            ("long", -0.002, False),  # crowded short helps a long
            # Short blocked only when funding below -threshold (crowded short).
            ("short", -0.001, True),
            ("short", -0.0008, False),
            ("short", -0.0005, False),
            ("short", 0.002, False),  # crowded long helps a short
            # Unknown funding never blocks.
            ("long", None, False),
            ("short", None, False),
        ],
    )
    def test_truth_table(self, direction: str, funding_rate: float | None, blocked: bool) -> None:
        assert funding_veto(direction, funding_rate, self.THRESHOLD) is blocked

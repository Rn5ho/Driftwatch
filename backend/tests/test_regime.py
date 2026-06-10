"""Regime classification and escalation-trigger tests (pure functions)."""

from app.analysis.regime import classify_regime
from app.config import settings
from app.pipeline import should_escalate
from app.schemas import ForecastOutput


def _forecast(**overrides) -> ForecastOutput:
    base = {
        "is_market_relevant": True,
        "category": "adoption",
        "asset": "BTC",
        "direction": "long",
        "probability": 0.5,
        "what_is_priced_in": "x",
        "thesis": "x",
        "key_risks": "x",
        "horizon_hours": 24,
    }
    base.update(overrides)
    return ForecastOutput(**base)


class TestClassifyRegime:
    def test_unknown_inputs_give_empty(self):
        assert classify_regime(None, 0.02) == ""
        assert classify_regime(0.01, None) == ""

    def test_uptrend_high_vol(self):
        assert classify_regime(0.08, 0.05) == "up/high_vol"

    def test_downtrend_low_vol(self):
        assert classify_regime(-0.10, 0.01) == "down/low_vol"

    def test_flat_at_thresholds(self):
        assert classify_regime(0.05, 0.04) == "flat/low_vol"
        assert classify_regime(-0.05, 0.04) == "flat/low_vol"


class TestShouldEscalate:
    def setup_method(self):
        self._saved = (
            settings.min_probability,
            settings.escalation_margin,
            settings.escalation_categories,
        )
        settings.min_probability = 0.60
        settings.escalation_margin = 0.05
        settings.escalation_categories = ["macro", "regulation"]

    def teardown_method(self):
        (
            settings.min_probability,
            settings.escalation_margin,
            settings.escalation_categories,
        ) = self._saved

    def test_near_tradeable_escalates(self):
        assert should_escalate(_forecast(probability=0.55))
        assert should_escalate(_forecast(probability=0.80))

    def test_below_margin_does_not_escalate(self):
        assert not should_escalate(_forecast(probability=0.54))

    def test_direction_none_never_near_tradeable(self):
        assert not should_escalate(_forecast(direction="none", probability=0.90))

    def test_high_stakes_category_escalates_regardless(self):
        assert should_escalate(_forecast(category="macro", probability=0.10))
        assert should_escalate(_forecast(category="macro", direction="none", probability=0.10))

    def test_low_stakes_low_probability_skips(self):
        assert not should_escalate(_forecast(category="adoption", probability=0.10))

"""Tests for legacy score → pseudo-state mapping."""

from quant.analysis.indicators.systemic_risk.legacy_map import (
    confidence_to_pseudo_state,
    risk_score_to_pseudo_state,
)


class TestRiskScoreMap:
    def test_crisis(self):
        assert risk_score_to_pseudo_state(80) == "confirmed"

    def test_tight(self):
        assert risk_score_to_pseudo_state(60) == "building"

    def test_normal(self):
        assert risk_score_to_pseudo_state(30) == "normal"

    def test_boundaries(self):
        assert risk_score_to_pseudo_state(75) == "confirmed"
        assert risk_score_to_pseudo_state(50) == "building"
        assert risk_score_to_pseudo_state(49.9) == "normal"


class TestConfidenceMap:
    def test_very_negative_confidence_is_confirmed(self):
        # confidence -100..+100; tight liquidity → negative
        assert confidence_to_pseudo_state(-60) == "confirmed"

    def test_mild_negative_building(self):
        assert confidence_to_pseudo_state(-20) == "building"

    def test_positive_normal(self):
        assert confidence_to_pseudo_state(10) == "normal"

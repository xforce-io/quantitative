#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Unit tests for RegimeDetector module.
Tests are written first (TDD) and cover all pools and edge cases.
"""

import pytest
from quant.analysis.regime.regime_detector import RegimeDetector, RegimeState


class TestRegimeState:
    def test_regime_state_creation(self):
        state = RegimeState(
            pool="a_shares",
            regime="risk-on",
            confidence=0.85,
            days_since_change=5,
            drivers=["margin_debt_trend is bullish", "northbound_flow is bullish"],
            updated_at="2026-04-12T00:00:00",
        )
        assert state.pool == "a_shares"
        assert state.regime == "risk-on"
        assert state.confidence == 0.85
        assert state.days_since_change == 5
        assert len(state.drivers) == 2
        assert state.updated_at == "2026-04-12T00:00:00"


class TestRegimeDetectorAShares:
    def setup_method(self):
        self.detector = RegimeDetector()

    def test_risk_on_when_all_bullish(self):
        indicators = {
            "margin_debt_trend": 3.0,
            "northbound_flow": 100.0,
            "market_breadth": 70.0,
            "china_risk_score": 30.0,
        }
        state = self.detector.classify_pool("a_shares", indicators)
        assert state.regime == "risk-on"
        assert state.confidence >= 0.6
        assert state.pool == "a_shares"

    def test_risk_off_when_all_bearish(self):
        indicators = {
            "margin_debt_trend": -5.0,
            "northbound_flow": -120.0,
            "market_breadth": 20.0,
            "china_risk_score": 80.0,
        }
        state = self.detector.classify_pool("a_shares", indicators)
        assert state.regime == "risk-off"
        assert state.confidence >= 0.6

    def test_transition_when_mixed(self):
        # Values between thresholds -> no decisive votes -> transition
        indicators = {
            "margin_debt_trend": 0.0,
            "northbound_flow": 0.0,
            "market_breadth": 45.0,
            "china_risk_score": 55.0,
        }
        state = self.detector.classify_pool("a_shares", indicators)
        assert state.regime == "transition"

    def test_drivers_list_populated(self):
        indicators = {
            "margin_debt_trend": 3.0,
            "northbound_flow": 100.0,
            "market_breadth": 70.0,
            "china_risk_score": 30.0,
        }
        state = self.detector.classify_pool("a_shares", indicators)
        assert len(state.drivers) > 0
        # Drivers should be human-readable strings
        for driver in state.drivers:
            assert isinstance(driver, str)
            assert len(driver) > 0

    def test_partial_indicators_still_classifies(self):
        # Only 2 of 4 indicators provided
        indicators = {
            "margin_debt_trend": 3.0,
            "northbound_flow": 100.0,
        }
        state = self.detector.classify_pool("a_shares", indicators)
        assert state.regime in ("risk-on", "risk-off", "transition")


class TestRegimeDetectorUSStocks:
    def setup_method(self):
        self.detector = RegimeDetector()

    def test_expansion_when_favorable(self):
        indicators = {
            "yield_curve_2s10s": 0.5,
            "credit_spread": 1.0,
            "vix": 15.0,
            "macro_risk_score": 30.0,
        }
        state = self.detector.classify_pool("us_stocks", indicators)
        assert state.regime == "expansion"
        assert state.confidence >= 0.6

    def test_contraction_when_stressed(self):
        indicators = {
            "yield_curve_2s10s": -0.8,
            "credit_spread": 3.0,
            "vix": 35.0,
            "macro_risk_score": 75.0,
        }
        state = self.detector.classify_pool("us_stocks", indicators)
        assert state.regime == "contraction"
        assert state.confidence >= 0.6

    def test_transition_when_mixed_us(self):
        indicators = {
            "yield_curve_2s10s": 0.5,   # positive
            "credit_spread": 3.0,        # negative
            "vix": 15.0,                 # positive
            "macro_risk_score": 75.0,    # negative
        }
        state = self.detector.classify_pool("us_stocks", indicators)
        assert state.regime == "transition"

    def test_pool_name_in_state(self):
        state = self.detector.classify_pool("us_stocks", {"vix": 15.0})
        assert state.pool == "us_stocks"


class TestRegimeDetectorGold:
    def setup_method(self):
        self.detector = RegimeDetector()

    def test_bullish_when_favorable(self):
        indicators = {
            "real_rate_10y": 0.5,       # below 1.0 threshold -> bullish
            "dxy_trend": -2.0,          # below -1.0 threshold -> bullish
            "gold_silver_ratio": 90.0,  # above 85.0 threshold -> bullish
        }
        state = self.detector.classify_pool("gold", indicators)
        assert state.regime == "bullish"
        assert state.confidence >= 0.6

    def test_bearish_when_unfavorable(self):
        indicators = {
            "real_rate_10y": 3.0,       # above 2.5 threshold -> bearish
            "dxy_trend": 3.0,           # above 2.0 threshold -> bearish
            "gold_silver_ratio": 60.0,  # below 65.0 threshold -> bearish
        }
        state = self.detector.classify_pool("gold", indicators)
        assert state.regime == "bearish"
        assert state.confidence >= 0.6

    def test_neutral_gold_when_mixed(self):
        indicators = {
            "real_rate_10y": 0.5,   # bullish
            "dxy_trend": 3.0,       # bearish
            "gold_silver_ratio": 75.0,  # neutral (between 65 and 85)
        }
        state = self.detector.classify_pool("gold", indicators)
        assert state.regime == "neutral"


class TestRegimeDetectorCommodities:
    def setup_method(self):
        self.detector = RegimeDetector()

    def test_reflation_when_strong(self):
        indicators = {
            "copper_gold_ratio": 2.0,   # above 0.0 -> reflation
            "crude_oil_trend": 8.0,     # above 5.0 -> reflation
            "dxy_trend": -2.0,          # below -1.0 -> reflation
        }
        state = self.detector.classify_pool("commodities", indicators)
        assert state.regime == "reflation"
        assert state.confidence >= 0.6

    def test_deflation_when_weak(self):
        indicators = {
            "copper_gold_ratio": -8.0,  # below -5.0 -> deflation
            "crude_oil_trend": -15.0,   # below -10.0 -> deflation
            "dxy_trend": 3.0,           # above 2.0 -> deflation
        }
        state = self.detector.classify_pool("commodities", indicators)
        assert state.regime == "deflation"
        assert state.confidence >= 0.6

    def test_neutral_commodities_when_mixed(self):
        indicators = {
            "copper_gold_ratio": 2.0,   # reflation
            "crude_oil_trend": -15.0,   # deflation
            "dxy_trend": 0.0,           # neutral (between thresholds)
        }
        state = self.detector.classify_pool("commodities", indicators)
        assert state.regime == "neutral"


class TestRegimeDetectorAllPools:
    def setup_method(self):
        self.detector = RegimeDetector()

    def test_classify_all_returns_four_states(self):
        all_indicators = {
            "a_shares": {
                "margin_debt_trend": 3.0,
                "northbound_flow": 100.0,
                "market_breadth": 70.0,
                "china_risk_score": 30.0,
            },
            "us_stocks": {
                "yield_curve_2s10s": 0.5,
                "credit_spread": 1.0,
                "vix": 15.0,
                "macro_risk_score": 30.0,
            },
            "gold": {
                "real_rate_10y": 0.5,
                "dxy_trend": -2.0,
                "gold_silver_ratio": 90.0,
            },
            "commodities": {
                "copper_gold_ratio": 2.0,
                "crude_oil_trend": 8.0,
                "dxy_trend": -2.0,
            },
        }
        results = self.detector.classify_all(all_indicators)
        assert len(results) == 4
        assert set(results.keys()) == {"a_shares", "us_stocks", "gold", "commodities"}
        for pool, state in results.items():
            assert isinstance(state, RegimeState)
            assert state.pool == pool

    def test_unknown_pool_raises(self):
        with pytest.raises(ValueError, match="Unknown pool"):
            self.detector.classify_pool("crypto", {})

    def test_confidence_between_zero_and_one(self):
        indicators = {
            "margin_debt_trend": 3.0,
            "northbound_flow": 100.0,
            "market_breadth": 70.0,
            "china_risk_score": 30.0,
        }
        state = self.detector.classify_pool("a_shares", indicators)
        assert 0.0 <= state.confidence <= 1.0

    def test_updated_at_is_iso_timestamp(self):
        state = self.detector.classify_pool("a_shares", {"margin_debt_trend": 3.0})
        # Should parse as ISO timestamp
        from datetime import datetime
        parsed = datetime.fromisoformat(state.updated_at)
        assert parsed is not None

    def test_days_since_change_defaults_to_none(self):
        state = self.detector.classify_pool("a_shares", {"margin_debt_trend": 3.0})
        # Without persistence we can't compute a real day count → must be None
        # (None = unknown; 0 would imply "regime just changed today").
        assert state.days_since_change is None

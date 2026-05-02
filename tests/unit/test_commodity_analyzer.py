#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Unit tests for CommodityAnalyzer — TDD first pass.
All tests are written before the implementation exists.
"""

import pytest
import numpy as np
import pandas as pd
from datetime import datetime

from quant.analysis.indicators.commodity_analyzer import CommodityAnalyzer


def _make_commodity_data(n_days=200, seed=42):
    """Generate synthetic commodity data."""
    rng = np.random.RandomState(seed)
    dates = pd.date_range(end=datetime.now(), periods=n_days, freq="B")
    gold = 2000 * np.exp(np.cumsum(rng.normal(0.0001, 0.008, n_days)))
    silver = gold / (75 + rng.normal(0, 3, n_days))
    copper = 4.0 * np.exp(np.cumsum(rng.normal(0.0001, 0.012, n_days)))
    crude = 75 * np.exp(np.cumsum(rng.normal(0, 0.015, n_days)))
    dxy = 105 * np.exp(np.cumsum(rng.normal(-0.0001, 0.005, n_days)))
    return {
        "gold": pd.Series(gold, index=dates),
        "silver": pd.Series(silver, index=dates),
        "copper": pd.Series(copper, index=dates),
        "crude_oil": pd.Series(crude, index=dates),
        "dxy": pd.Series(dxy, index=dates),
    }


class TestCommodityAnalyzer:

    def setup_method(self):
        self.analyzer = CommodityAnalyzer()
        self.data = _make_commodity_data()

    def test_analyze_returns_all_indicators(self):
        result = self.analyzer.analyze(self.data)
        expected_keys = [
            "gold_silver_ratio",
            "copper_gold_ratio",
            "gold_roc_20d",
            "crude_oil_roc_20d",
            "dxy_roc_20d",
            "copper_roc_20d",
            "analyzed_at",
        ]
        for key in expected_keys:
            assert key in result, f"Missing key: {key}"

    def test_gold_silver_ratio_reasonable(self):
        result = self.analyzer.analyze(self.data)
        ratio = result["gold_silver_ratio"]
        assert ratio is not None
        assert 50 <= ratio <= 120, f"gold_silver_ratio {ratio} out of expected range 50-120"

    def test_roc_is_percentage(self):
        result = self.analyzer.analyze(self.data)
        for key in ("gold_roc_20d", "crude_oil_roc_20d", "dxy_roc_20d", "copper_roc_20d"):
            value = result[key]
            assert value is not None, f"{key} should not be None"
            assert -50 <= value <= 50, f"{key}={value} out of expected range -50..50"

    def test_values_rounded_to_2_decimal_places(self):
        result = self.analyzer.analyze(self.data)
        for key in ("gold_silver_ratio", "gold_roc_20d", "crude_oil_roc_20d", "dxy_roc_20d", "copper_roc_20d"):
            value = result[key]
            if value is not None:
                assert value == round(value, 2), f"{key}={value} not rounded to 2 decimal places"

    def test_analyzed_at_is_string(self):
        result = self.analyzer.analyze(self.data)
        assert isinstance(result["analyzed_at"], str)
        # Should be parseable as ISO datetime
        datetime.fromisoformat(result["analyzed_at"])

    def test_copper_gold_ratio_is_normalized(self):
        # copper_gold_ratio is normalized: (current / 60d_mean - 1) * 100
        # So it should be a percentage deviation, not an absolute ratio
        result = self.analyzer.analyze(self.data)
        ratio = result["copper_gold_ratio"]
        assert ratio is not None
        # Normalized deviation from 60d mean — should be within ±50% for typical data
        assert -50 <= ratio <= 50, f"copper_gold_ratio {ratio} out of expected range"

    def test_regime_indicators_for_gold(self):
        result = self.analyzer.get_regime_indicators("gold", self.data)
        assert "gold_silver_ratio" in result
        assert "dxy_trend" in result
        assert isinstance(result["gold_silver_ratio"], (int, float))
        assert isinstance(result["dxy_trend"], (int, float))

    def test_regime_indicators_for_commodities(self):
        result = self.analyzer.get_regime_indicators("commodities", self.data)
        assert "copper_gold_ratio" in result
        assert "crude_oil_trend" in result
        assert "dxy_trend" in result
        assert isinstance(result["copper_gold_ratio"], (int, float))
        assert isinstance(result["crude_oil_trend"], (int, float))
        assert isinstance(result["dxy_trend"], (int, float))

    def test_empty_data_handles_gracefully(self):
        result = self.analyzer.analyze({})
        assert "error" in result

    def test_missing_single_series_returns_none_for_that_indicator(self):
        # Remove silver → gold_silver_ratio should be None
        data = {k: v for k, v in self.data.items() if k != "silver"}
        result = self.analyzer.analyze(data)
        assert result.get("gold_silver_ratio") is None

    def test_missing_dxy_leaves_other_indicators_intact(self):
        data = {k: v for k, v in self.data.items() if k != "dxy"}
        result = self.analyzer.analyze(data)
        assert result.get("dxy_roc_20d") is None
        # Other indicators that don't need dxy should still be present
        assert result.get("gold_silver_ratio") is not None
        assert result.get("gold_roc_20d") is not None

    def test_insufficient_data_for_roc_returns_none(self):
        # Only 5 days of data — can't compute 20d ROC (needs 21 data points)
        short_data = {k: v.iloc[-5:] for k, v in self.data.items()}
        result = self.analyzer.analyze(short_data)
        assert result.get("gold_roc_20d") is None

    def test_regime_indicators_unknown_pool_returns_empty(self):
        result = self.analyzer.get_regime_indicators("unknown_pool", self.data)
        assert result == {}

    def test_roc_calculation_is_correct(self):
        # Build a deterministic series: constant value => ROC = 0
        dates = pd.date_range(end=datetime.now(), periods=100, freq="B")
        const = pd.Series(np.ones(100) * 1800.0, index=dates)
        data = {**self.data, "gold": const}
        result = self.analyzer.analyze(data)
        assert result["gold_roc_20d"] == 0.0

    def test_gold_silver_ratio_aligned_on_common_dates(self):
        # Stagger index by 1 day for silver — should still compute on intersection
        data = dict(self.data)
        data["silver"] = data["silver"].iloc[1:]  # drop first date
        result = self.analyzer.analyze(data)
        # Should still produce a valid ratio
        assert result["gold_silver_ratio"] is not None

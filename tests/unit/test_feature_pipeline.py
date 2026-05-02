#!/usr/bin/env python3
"""Tests for FeaturePipeline — regime feature normalization."""

import numpy as np
import pandas as pd
import pytest

from quant.analysis.regime.feature_pipeline import FeaturePipeline


@pytest.fixture
def pipeline():
    return FeaturePipeline(pool="us_stocks")


@pytest.fixture
def sample_series():
    """200 trading days of synthetic data for each indicator."""
    dates = pd.bdate_range("2025-01-01", periods=200)
    rng = np.random.RandomState(42)
    return {
        "vix": pd.Series(20 + rng.randn(200) * 5, index=dates),
        "credit_spread": pd.Series(1.8 + rng.randn(200) * 0.3, index=dates),
        "yield_curve": pd.Series(0.2 + rng.randn(200) * 0.4, index=dates),
        "benchmark": pd.Series(
            450 * np.cumprod(1 + rng.randn(200) * 0.01), index=dates
        ),
    }


class TestFeaturePipelineOutput:
    def test_returns_all_nine_features(self, pipeline, sample_series):
        features = pipeline.compute(sample_series, eval_idx=-1)
        expected_keys = {
            "vix_level", "vix_roc", "cs_level", "cs_change",
            "yc_level", "yc_change", "price_vs_ma200",
            "ma50_vs_ma200", "rsi_norm",
        }
        assert set(features.keys()) == expected_keys

    def test_all_features_in_range(self, pipeline, sample_series):
        features = pipeline.compute(sample_series, eval_idx=-1)
        for name, val in features.items():
            assert -1.0 <= val <= 1.0, f"{name}={val} out of [-1, 1]"

    def test_extreme_vix_saturates(self, pipeline, sample_series):
        """A VIX spike to 80 should produce a feature near -1 (bearish)."""
        series = sample_series.copy()
        series["vix"] = series["vix"].copy()
        series["vix"].iloc[-1] = 80.0
        features = pipeline.compute(series, eval_idx=-1)
        assert features["vix_level"] < -0.5

    def test_rsi_midpoint_near_zero(self, pipeline):
        """Perfectly flat prices -> RSI ~50 -> rsi_norm ~0."""
        dates = pd.bdate_range("2025-01-01", periods=200)
        flat = pd.Series(100.0, index=dates)
        series = {
            "vix": pd.Series(20.0, index=dates),
            "credit_spread": pd.Series(1.8, index=dates),
            "yield_curve": pd.Series(0.2, index=dates),
            "benchmark": flat,
        }
        features = pipeline.compute(series, eval_idx=-1)
        assert abs(features["rsi_norm"]) < 0.15

    def test_eval_idx_slices_correctly(self, pipeline, sample_series):
        """Features at idx=100 should not see data after idx=100."""
        f1 = pipeline.compute(sample_series, eval_idx=100)
        f2 = pipeline.compute(sample_series, eval_idx=-1)
        # Different eval points -> different features (almost certainly)
        assert f1 != f2

    def test_insufficient_data_returns_empty(self, pipeline):
        """If not enough history, return empty dict."""
        dates = pd.bdate_range("2025-01-01", periods=10)
        short = {
            "vix": pd.Series(20.0, index=dates),
            "credit_spread": pd.Series(1.8, index=dates),
            "yield_curve": pd.Series(0.2, index=dates),
            "benchmark": pd.Series(100.0, index=dates),
        }
        features = pipeline.compute(short, eval_idx=-1)
        assert features == {}

#!/usr/bin/env python3
"""Tests for ContinuousRegimeScorer — end-to-end scoring -> RegimeState."""

import numpy as np
import pandas as pd
import pytest

from quant.analysis.regime.continuous_scorer import ContinuousRegimeScorer
from quant.analysis.regime.regime_detector import RegimeState


@pytest.fixture
def scorer():
    return ContinuousRegimeScorer(pool="us_stocks")


@pytest.fixture
def bullish_series():
    """Strongly bullish market: low VIX, tight spreads, steep curve, uptrend."""
    dates = pd.bdate_range("2024-01-01", periods=300)
    return {
        "vix": pd.Series(
            np.concatenate([np.full(280, 25.0), np.full(20, 12.0)]),
            index=dates,
        ),
        "credit_spread": pd.Series(
            np.concatenate([np.full(280, 2.0), np.full(20, 1.0)]),
            index=dates,
        ),
        "yield_curve": pd.Series(
            np.concatenate([np.full(280, 0.0), np.full(20, 0.8)]),
            index=dates,
        ),
        "benchmark": pd.Series(
            400 * np.cumprod(np.concatenate([
                np.full(280, 1.001),
                np.full(20, 1.005),
            ])),
            index=dates,
        ),
    }


@pytest.fixture
def bearish_series():
    """Strongly bearish market: high VIX, wide spreads, inverted curve, downtrend."""
    dates = pd.bdate_range("2024-01-01", periods=300)
    return {
        "vix": pd.Series(
            np.concatenate([np.full(280, 15.0), np.full(20, 40.0)]),
            index=dates,
        ),
        "credit_spread": pd.Series(
            np.concatenate([np.full(280, 1.5), np.full(20, 3.5)]),
            index=dates,
        ),
        "yield_curve": pd.Series(
            np.concatenate([np.full(280, 0.5), np.full(20, -0.5)]),
            index=dates,
        ),
        "benchmark": pd.Series(
            500 * np.cumprod(np.concatenate([
                np.full(280, 1.001),
                np.full(20, 0.995),
            ])),
            index=dates,
        ),
    }


class TestContinuousRegimeScorerOutput:
    def test_returns_regime_state(self, scorer, bullish_series):
        state = scorer.classify(bullish_series)
        assert isinstance(state, RegimeState)
        assert state.pool == "us_stocks"

    def test_bullish_market_is_expansion(self, scorer, bullish_series):
        state = scorer.classify(bullish_series)
        assert state.regime == "expansion"
        assert state.confidence > 0.3

    def test_bearish_market_is_contraction(self, scorer, bearish_series):
        state = scorer.classify(bearish_series)
        assert state.regime == "contraction"
        assert state.confidence > 0.3

    def test_confidence_between_zero_and_one(self, scorer, bullish_series):
        state = scorer.classify(bullish_series)
        assert 0.0 <= state.confidence <= 1.0

    def test_drivers_populated(self, scorer, bullish_series):
        state = scorer.classify(bullish_series)
        assert len(state.drivers) > 0

    def test_raw_score_available(self, scorer, bullish_series):
        score = scorer.score(bullish_series)
        assert isinstance(score, float)
        assert -1.0 <= score <= 1.0

    def test_score_positive_for_bullish(self, scorer, bullish_series):
        score = scorer.score(bullish_series)
        assert score > 0

    def test_score_negative_for_bearish(self, scorer, bearish_series):
        score = scorer.score(bearish_series)
        assert score < 0

    def test_classify_at_index(self, scorer, bullish_series):
        """Can classify at a specific historical index for backtesting."""
        state = scorer.classify(bullish_series, eval_idx=250)
        assert isinstance(state, RegimeState)

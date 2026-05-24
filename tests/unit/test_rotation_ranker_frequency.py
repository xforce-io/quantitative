"""MomentumRanker frequency-parameterization tests."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from quant.analysis.rotation.ranker import MomentumRanker, RankerConfig


def _weekly_prices(growth: dict[str, float]) -> pd.DataFrame:
    """52 weeks of constant weekly growth."""
    weeks = pd.date_range("2024-01-05", periods=52, freq="W-FRI")
    data = {sym: 100.0 * (1 + g) ** np.arange(52) for sym, g in growth.items()}
    return pd.DataFrame(data, index=weeks)


def test_weekly_lookback_uses_26_bars_for_6_months() -> None:
    """lookback_months=6 at frequency=weekly should look back 26 bars."""
    prices = _weekly_prices({"A": 0.01, "B": -0.01})
    ranker = MomentumRanker(
        RankerConfig(lookback_months=6, skip_recent_months=0, top_k=1, cash_threshold=-1.0),
        frequency="weekly",
    )
    weights = ranker.rank(prices, prices.index[-1])
    # A grows, B shrinks — A should be picked.
    assert set(weights) == {"A"}


def test_weekly_insufficient_history_returns_empty() -> None:
    """At rebalance bar < 26 + skip(4), ranker has no history at weekly."""
    prices = _weekly_prices({"A": 0.01})
    ranker = MomentumRanker(
        RankerConfig(lookback_months=6, skip_recent_months=1, top_k=1, cash_threshold=-1.0),
        frequency="weekly",
    )
    # 26 lookback + 4 skip = 30; index 29 (0-based) is borderline (29-4=25, 25-26=-1 → empty)
    assert ranker.rank(prices, prices.index[29]) == {}
    # Index 30+ should produce non-empty
    assert ranker.rank(prices, prices.index[30]) != {}


def test_monthly_default_unchanged() -> None:
    """frequency defaults to monthly; existing monthly behavior unchanged."""
    months = pd.date_range("2022-01-31", periods=24, freq="ME")
    prices = pd.DataFrame(
        {"A": 100.0 * 1.05 ** np.arange(24), "B": 100.0 * 0.99 ** np.arange(24)},
        index=months,
    )
    ranker = MomentumRanker(RankerConfig(top_k=1, cash_threshold=-1.0))  # no frequency arg
    weights = ranker.rank(prices, prices.index[-1])
    assert set(weights) == {"A"}


def test_multifactor_weekly_lookback() -> None:
    """MultiFactorRanker honors frequency for per-factor lookback_months."""
    from quant.analysis.rotation.ranker import MultiFactorRanker

    weeks = pd.date_range("2023-01-06", periods=60, freq="W-FRI")
    prices = pd.DataFrame(
        {
            "A": 100.0 * 1.01 ** np.arange(60),
            "B": 100.0 * 1.005 ** np.arange(60),
            "C": 100.0 * 0.995 ** np.arange(60),
        },
        index=weeks,
    )
    risk_on_alloc = {
        "top_k": 1,
        "multi_factor_config": {
            "rank_normalization": "cross_sectional_percentile",
            "composite_score": "weighted_average_of_ranks",
            "factors": [
                {"name": "momentum", "weight": 1.0, "lookback_months": 6, "skip_months": 1},
            ],
        },
    }
    ranker = MultiFactorRanker(risk_on_alloc, frequency="weekly")
    weights = ranker.rank(prices, prices.index[-1])
    assert set(weights) == {"A"}

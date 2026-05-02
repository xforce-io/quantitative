"""Tests for MomentumRanker."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from quant.analysis.rotation.ranker import MomentumRanker, RankerConfig


def _monthly_prices_with_known_momentum(growth: dict[str, float]) -> pd.DataFrame:
    """Build a 24-month price frame where each symbol has constant monthly growth."""
    months = pd.date_range("2022-01-31", periods=24, freq="ME")
    data = {sym: 100.0 * (1 + g) ** np.arange(24) for sym, g in growth.items()}
    return pd.DataFrame(data, index=months)


def test_top_k_selects_highest_12_1_momentum() -> None:
    prices = _monthly_prices_with_known_momentum(
        {"A": 0.05, "B": 0.04, "C": 0.03, "D": 0.02, "E": 0.01, "F": -0.01}
    )
    ranker = MomentumRanker(RankerConfig(top_k=3))
    weights = ranker.rank(prices, prices.index[-1])
    assert set(weights) == {"A", "B", "C"}
    assert pytest.approx(sum(weights.values()), abs=1e-9) == 1.0
    for w in weights.values():
        assert pytest.approx(w, abs=1e-9) == 1.0 / 3


def test_cash_filter_returns_empty_when_top_k_mean_below_threshold() -> None:
    prices = _monthly_prices_with_known_momentum(
        {"A": -0.01, "B": -0.02, "C": -0.03, "D": -0.04, "E": -0.05}
    )
    ranker = MomentumRanker(RankerConfig(top_k=3, cash_threshold=0.0))
    weights = ranker.rank(prices, prices.index[-1])
    assert weights == {}


def test_insufficient_history_excluded_from_ranking() -> None:
    prices = _monthly_prices_with_known_momentum(
        {"A": 0.05, "B": 0.04, "C": 0.03}
    )
    prices.loc[prices.index[:12], "B"] = np.nan

    ranker = MomentumRanker(RankerConfig(top_k=3))
    weights = ranker.rank(prices, prices.index[-1])
    assert "B" not in weights
    assert set(weights) <= {"A", "C"}


def test_explicit_12_1_formula() -> None:
    """Verify momentum = price[t-1] / price[t-13] - 1 exactly."""
    prices = pd.DataFrame(
        {
            "X": [100.0] * 13 + [200.0],
            "Y": [100.0] * 14,
        },
        index=pd.date_range("2024-01-31", periods=14, freq="ME"),
    )
    ranker = MomentumRanker(RankerConfig(top_k=2, cash_threshold=-1.0))
    weights = ranker.rank(prices, prices.index[-1])
    assert set(weights) == {"X", "Y"}


def test_empty_universe_at_rebalance_returns_empty() -> None:
    prices = pd.DataFrame(
        {"A": [np.nan] * 24}, index=pd.date_range("2022-01-31", periods=24, freq="ME")
    )
    ranker = MomentumRanker(RankerConfig(top_k=3))
    weights = ranker.rank(prices, prices.index[-1])
    assert weights == {}


def test_rebalance_date_must_exist_in_index() -> None:
    prices = _monthly_prices_with_known_momentum({"A": 0.05, "B": 0.04})
    ranker = MomentumRanker()
    with pytest.raises(KeyError):
        ranker.rank(prices, pd.Timestamp("1999-01-31"))

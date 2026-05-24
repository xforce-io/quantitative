"""Tests for RotationBacktester."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from quant.analysis.rotation.backtest import (
    RotationBacktestConfig,
    RotationBacktester,
)
from quant.analysis.rotation.portfolio import PortfolioCombiner


class _FixedRanker:
    """Always pick the same single symbol with weight 1.0."""

    def __init__(self, symbol: str) -> None:
        self.symbol = symbol

    def rank(self, monthly_prices: pd.DataFrame, rebalance_date: pd.Timestamp) -> dict[str, float]:
        return {self.symbol: 1.0}


class _AlwaysFullOverlay:
    def multiplier_at(self, date: pd.Timestamp) -> float:
        return 1.0


class _AlwaysHalfOverlay:
    def multiplier_at(self, date: pd.Timestamp) -> float:
        return 0.5


def _multi_asset_monthly_prices() -> pd.DataFrame:
    months = pd.date_range("2022-01-31", periods=24, freq="ME")
    return pd.DataFrame(
        {
            "A": 100.0 * (1.05 ** np.arange(24)),
            "B": 100.0 * (1.03 ** np.arange(24)),
            "C": 100.0 * np.ones(24),
        },
        index=months,
    )


def test_backtest_returns_metrics_and_curves() -> None:
    prices = _multi_asset_monthly_prices()
    benchmark = pd.Series(
        100.0 * (1.02 ** np.arange(24)), index=prices.index, name="benchmark"
    )
    bt = RotationBacktester(RotationBacktestConfig(transaction_cost=0.0))
    result = bt.run(
        universe_prices=prices,
        benchmark_prices=benchmark,
        ranker=_FixedRanker("A"),
        overlay=_AlwaysFullOverlay(),
        combiner=PortfolioCombiner(),
    )
    assert {
        "total_return_strategy",
        "total_return_benchmark",
        "total_return_equal_weight",
        "annual_return_strategy",
        "annual_vol_strategy",
        "max_drawdown_strategy",
        "sharpe_strategy",
    } <= set(result.metrics)
    assert {"strategy", "benchmark", "equal_weight"} == set(result.equity_curve.columns)
    assert {"strategy", "benchmark", "equal_weight", "turnover"} <= set(
        result.monthly_returns.columns
    )
    assert result.holdings.shape[0] == len(prices)


def test_strategy_compounds_to_match_held_asset_with_zero_cost() -> None:
    """Holding A from month 1 onward with no cost; strategy curve == A's normalized curve."""
    prices = _multi_asset_monthly_prices()
    benchmark = pd.Series(100.0 * np.ones(24), index=prices.index)
    bt = RotationBacktester(RotationBacktestConfig(transaction_cost=0.0))
    result = bt.run(
        universe_prices=prices,
        benchmark_prices=benchmark,
        ranker=_FixedRanker("A"),
        overlay=_AlwaysFullOverlay(),
        combiner=PortfolioCombiner(),
    )
    # A's prices normalized to start at 1.0
    expected = prices["A"] / prices["A"].iloc[0]
    np.testing.assert_allclose(
        result.equity_curve["strategy"].values,
        expected.values,
        rtol=1e-9,
    )


def test_half_multiplier_dampens_return() -> None:
    prices = _multi_asset_monthly_prices()
    benchmark = pd.Series(100.0 * np.ones(24), index=prices.index)
    bt = RotationBacktester(RotationBacktestConfig(transaction_cost=0.0))
    full = bt.run(prices, benchmark, _FixedRanker("A"), _AlwaysFullOverlay(), PortfolioCombiner())
    half = bt.run(prices, benchmark, _FixedRanker("A"), _AlwaysHalfOverlay(), PortfolioCombiner())
    assert half.metrics["annual_return_strategy"] < full.metrics["annual_return_strategy"]


def test_transaction_cost_reduces_return() -> None:
    prices = _multi_asset_monthly_prices()
    benchmark = pd.Series(100.0 * np.ones(24), index=prices.index)
    no_cost = RotationBacktester(RotationBacktestConfig(transaction_cost=0.0)).run(
        prices, benchmark, _FixedRanker("A"), _AlwaysFullOverlay(), PortfolioCombiner()
    )
    with_cost = RotationBacktester(RotationBacktestConfig(transaction_cost=0.01)).run(
        prices, benchmark, _FixedRanker("A"), _AlwaysFullOverlay(), PortfolioCombiner()
    )
    # Compare the unrounded final equity values; metrics dict rounds to 4 decimals
    assert (
        with_cost.equity_curve["strategy"].iloc[-1]
        < no_cost.equity_curve["strategy"].iloc[-1]
    )


def test_empty_ranker_yields_flat_strategy() -> None:
    prices = _multi_asset_monthly_prices()
    benchmark = pd.Series(100.0 * np.ones(24), index=prices.index)

    class _EmptyRanker:
        def rank(self, mp, d):
            return {}

    bt = RotationBacktester(RotationBacktestConfig(transaction_cost=0.0))
    result = bt.run(prices, benchmark, _EmptyRanker(), _AlwaysFullOverlay(), PortfolioCombiner())
    np.testing.assert_allclose(
        result.equity_curve["strategy"].values,
        np.ones(len(prices)),
        rtol=1e-9,
    )


def test_turnover_l1_formula() -> None:
    """Turnover_t = 0.5 * sum(|w_t - w_{t-1}|).  Verify on a fixed schedule."""
    prices = _multi_asset_monthly_prices()
    benchmark = pd.Series(100.0 * np.ones(24), index=prices.index)

    class _AlternatingRanker:
        def __init__(self) -> None:
            self.calls = 0

        def rank(self, mp, d):
            self.calls += 1
            return {"A": 1.0} if self.calls % 2 == 1 else {"B": 1.0}

    bt = RotationBacktester(RotationBacktestConfig(transaction_cost=0.0))
    result = bt.run(prices, benchmark, _AlternatingRanker(), _AlwaysFullOverlay(), PortfolioCombiner())
    assert pytest.approx(result.monthly_returns["turnover"].iloc[0], abs=1e-9) == 0.5
    assert pytest.approx(result.monthly_returns["turnover"].iloc[1], abs=1e-9) == 1.0


def test_backtester_weekly_annualization() -> None:
    """Annual return formula uses bars_per_year(freq), not hardcoded 12."""
    import numpy as np
    import pandas as pd
    from quant.analysis.rotation.backtest import RotationBacktester, RotationBacktestConfig

    weeks = pd.date_range("2024-01-05", periods=52, freq="W-FRI")
    universe = pd.DataFrame({"A": 100.0 * 1.01 ** np.arange(52)}, index=weeks)
    benchmark = pd.Series(100.0 * 1.005 ** np.arange(52), index=weeks)

    class _Ranker:
        def rank(self, prices, date): return {"A": 1.0}
    class _Overlay:
        def multiplier_at(self, date): return 1.0
    class _Combiner:
        def combine(self, weights, mult): return {k: v * mult for k, v in weights.items()}

    cfg = RotationBacktestConfig(frequency="weekly", transaction_cost=0.0)
    bt = RotationBacktester(cfg)
    result = bt.run(universe, benchmark, _Ranker(), _Overlay(), _Combiner())
    # 1% weekly compounded 52 weeks ≈ (1.01)^52 - 1 ≈ 0.6777
    assert 0.65 < result.metrics["annual_return_strategy"] < 0.71

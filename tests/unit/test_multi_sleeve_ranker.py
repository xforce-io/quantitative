"""Unit tests for multi-sleeve rotation rankers."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from quant.analysis.rotation.multi_sleeve import (
    MinHoldRanker,
    MultiSleeveRanker,
    PortfolioLevelCBRanker,
    build_ranker_from_spec,
    make_ranker_cfg,
)
from quant.analysis.rotation.ranker import MomentumRanker


def _monthly_frame(symbols: dict[str, list[float]], start: str = "2020-01-31") -> pd.DataFrame:
    n = len(next(iter(symbols.values())))
    index = pd.date_range(start, periods=n, freq="ME")
    return pd.DataFrame(symbols, index=index)


def _bench_from_prices(prices: pd.DataFrame, col: str | None = None) -> pd.Series:
    if col and col in prices.columns:
        return prices[col].copy()
    # Rising then flat/falling benchmark for regime tests
    return prices.iloc[:, 0].copy()


class TestMinHoldRanker:
    def test_min_hold_blocks_switch_within_window(self) -> None:
        prices = _monthly_frame(
            {
                "A": [10, 11, 12, 13, 14, 20, 21, 22, 23, 24],
                "B": [10, 12, 14, 16, 18, 15, 14, 13, 12, 11],
            }
        )
        # Pure momentum would prefer B early then A later; min_hold=3 freezes first pick.
        inner = MomentumRanker(make_ranker_cfg({"lookback_months": 2, "skip_months": 0, "top_k": 1}))
        ranker = MinHoldRanker(inner, min_hold_months=3)

        d0 = prices.index[4]
        first = ranker.rank(prices, d0)
        assert len(first) == 1
        held = next(iter(first))

        d1 = prices.index[5]
        second = ranker.rank(prices, d1)
        assert second == first
        assert next(iter(second)) == held


class TestMultiSleeveRanker:
    def test_risk_on_selects_from_industry_sleeve(self) -> None:
        # Benchmark rising strongly -> risk_on
        n = 18
        prices = _monthly_frame(
            {
                "IND_A": list(np.linspace(100, 200, n)),  # strong
                "IND_B": list(np.linspace(100, 120, n)),
                "DEF_A": list(np.linspace(100, 105, n)),
                "511880.SH": list(np.linspace(100, 102, n)),
            }
        )
        bench = prices["IND_A"]  # strong up
        sleeve_map = {
            "industry": ["IND_A", "IND_B"],
            "defensive_global": ["DEF_A", "511880.SH"],
        }
        ranker = MultiSleeveRanker(
            monthly_benchmark=bench,
            risk_on_rule={
                "method": "simple_threshold",
                "lookback_months": 6,
                "min_return": 0.0,
            },
            risk_on_allocation={
                "sleeve": "industry",
                "lookback_months": 6,
                "skip_months": 1,
                "top_k": 1,
                "min_hold_months": 1,
                "momentum_score_method": "pure_momentum",
            },
            risk_off_allocation={
                "mode": "fixed",
                "weights": {"511880.SH": 1.0},
            },
            sleeve_map=sleeve_map,
            factor_store=None,
        )
        date = prices.index[-1]
        assert ranker._is_risk_on(prices, date) is True
        weights = ranker.rank(prices, date)
        assert set(weights) <= {"IND_A", "IND_B"}
        assert abs(sum(weights.values()) - 1.0) < 1e-9

    def test_risk_off_uses_fixed_weights(self) -> None:
        n = 18
        # Falling benchmark -> risk_off
        prices = _monthly_frame(
            {
                "IND_A": list(np.linspace(200, 100, n)),
                "511880.SH": list(np.linspace(100, 101, n)),
            }
        )
        bench = prices["IND_A"]
        ranker = MultiSleeveRanker(
            monthly_benchmark=bench,
            risk_on_rule={
                "method": "simple_threshold",
                "lookback_months": 6,
                "min_return": 0.0,
            },
            risk_on_allocation={
                "sleeve": "industry",
                "lookback_months": 6,
                "skip_months": 1,
                "top_k": 1,
                "momentum_score_method": "pure_momentum",
            },
            risk_off_allocation={
                "mode": "fixed",
                "weights": {"511880.SH": 1.0},
            },
            sleeve_map={"industry": ["IND_A"]},
            factor_store=None,
        )
        date = prices.index[-1]
        assert ranker._is_risk_on(prices, date) is False
        weights = ranker.rank(prices, date)
        assert weights == {"511880.SH": 1.0}

    def test_risk_off_floor_rule_when_all_momentum_negative(self) -> None:
        n = 18
        prices = _monthly_frame(
            {
                "IND_A": list(np.linspace(200, 100, n)),
                "GOLD": list(np.linspace(120, 100, n)),  # negative momentum
                "511880.SH": list(np.linspace(100, 101, n)),
            }
        )
        bench = prices["IND_A"]
        ranker = MultiSleeveRanker(
            monthly_benchmark=bench,
            risk_on_rule={
                "method": "simple_threshold",
                "lookback_months": 6,
                "min_return": 0.0,
            },
            risk_on_allocation={
                "sleeve": "industry",
                "lookback_months": 6,
                "skip_months": 1,
                "top_k": 1,
                "momentum_score_method": "pure_momentum",
            },
            risk_off_allocation={
                "mode": "momentum_rotation",
                "lookback_months": 6,
                "skip_months": 0,
                "top_k": 1,
                "min_hold_months": 1,
                "candidates": [{"real_etf": "GOLD"}],
                "floor_rule": {
                    "enabled": True,
                    "fallback_asset": "511880.SH",
                },
            },
            sleeve_map={"industry": ["IND_A"]},
            factor_store=None,
        )
        # cash_threshold default 0: negative momentum -> empty -> floor
        # MomentumRanker cash_threshold is 0.0, mean negative => empty
        date = prices.index[-1]
        weights = ranker.rank(prices, date)
        assert weights == {"511880.SH": 1.0}

    def test_multi_factor_risk_on_top_k_equal_weight(self) -> None:
        n = 18
        prices = _monthly_frame(
            {
                "A": list(np.linspace(100, 180, n)),
                "B": list(np.linspace(100, 160, n)),
                "C": list(np.linspace(100, 140, n)),
                "D": list(np.linspace(100, 110, n)),
            }
        )
        # Low vol prefers smoother series; all linear so similar vol. Momentum dominates.
        bench = prices["A"]
        ranker = MultiSleeveRanker(
            monthly_benchmark=bench,
            risk_on_rule={
                "method": "simple_threshold",
                "lookback_months": 6,
                "min_return": 0.0,
            },
            risk_on_allocation={
                "sleeve": "industry",
                "top_k": 2,
                "min_hold_months": 1,
                "momentum_score_method": "multi_factor_rank",
                "multi_factor_config": {
                    "factors": [
                        {"name": "momentum", "weight": 0.5, "lookback_months": 6, "skip_months": 1},
                        {"name": "low_volatility", "weight": 0.3, "lookback_months": 6},
                        {
                            "name": "relative_strength",
                            "weight": 0.2,
                            "lookback_months": 6,
                            "skip_months": 1,
                        },
                    ]
                },
            },
            risk_off_allocation={"mode": "fixed", "weights": {"D": 1.0}},
            sleeve_map={"industry": ["A", "B", "C", "D"]},
            factor_store=None,
        )
        weights = ranker.rank(prices, prices.index[-1])
        assert len(weights) == 2
        assert abs(sum(weights.values()) - 1.0) < 1e-9
        assert all(abs(w - 0.5) < 1e-9 for w in weights.values())


class TestPortfolioLevelCBRanker:
    def test_triggers_only_in_risk_off_after_drawdown(self) -> None:
        n = 20
        # First half rising (risk_on), then crash (risk_off) while holding crash asset
        ind = list(np.linspace(100, 150, 10)) + list(np.linspace(150, 50, 10))
        bond = [100.0] * n
        crash = list(np.linspace(100, 160, 10)) + list(np.linspace(160, 40, 10))
        prices = _monthly_frame(
            {
                "IND": ind,
                "CRASH": crash,
                "511880.SH": bond,
            }
        )
        bench = prices["IND"]
        inner = MultiSleeveRanker(
            monthly_benchmark=bench,
            risk_on_rule={
                "method": "simple_threshold",
                "lookback_months": 3,
                "min_return": 0.0,
            },
            risk_on_allocation={
                "sleeve": "industry",
                "lookback_months": 3,
                "skip_months": 0,
                "top_k": 1,
                "momentum_score_method": "pure_momentum",
            },
            risk_off_allocation={
                "mode": "fixed",
                "weights": {"CRASH": 1.0},
            },
            sleeve_map={"industry": ["IND"]},
            factor_store=None,
        )
        cb = PortfolioLevelCBRanker(inner, threshold=-0.20, fallback_asset="511880.SH")

        last_weights = {}
        for date in prices.index:
            last_weights = cb.rank(prices, date)

        # After deep drawdown in risk_off, should force bond
        assert last_weights == {"511880.SH": 1.0}
        assert len(cb.stats["portfolio_cb_triggers"]) >= 1


class TestBuildRankerFromSpec:
    def test_build_with_portfolio_cb_wrapper(self) -> None:
        n = 12
        prices = _monthly_frame(
            {
                "A": list(np.linspace(100, 120, n)),
                "511880.SH": [100.0] * n,
            }
        )
        spec = {
            "risk_on_rule": {
                "method": "simple_threshold",
                "lookback_months": 3,
                "min_return": 0.0,
            },
            "risk_on_allocation": {
                "sleeve": "industry",
                "lookback_months": 3,
                "skip_months": 0,
                "top_k": 1,
                "momentum_score_method": "pure_momentum",
            },
            "risk_off_allocation": {
                "mode": "fixed",
                "weights": {"511880.SH": 1.0},
                "portfolio_trailing_drawdown_circuit_breaker": {
                    "enabled": True,
                    "threshold": -0.25,
                    "fallback_asset": "511880.SH",
                },
            },
        }
        ranker = build_ranker_from_spec(
            spec,
            monthly_benchmark=prices["A"],
            sleeve_map={"industry": ["A"]},
            factor_store=None,
            enable_portfolio_cb=True,
        )
        assert isinstance(ranker, PortfolioLevelCBRanker)
        weights = ranker.rank(prices, prices.index[-1])
        assert abs(sum(weights.values()) - 1.0) < 1e-9

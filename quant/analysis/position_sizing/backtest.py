#!/usr/bin/env python3
"""PositionSizingBacktest — weekly rebalancing simulation vs buy-and-hold."""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd

from quant.analysis.position_sizing.volatility import VolatilityCalculator

WEEKS_PER_YEAR = 52


@dataclass
class BacktestResult:
    """Summary statistics comparing strategy vs buy-and-hold."""

    annual_return_strategy: float
    annual_return_benchmark: float
    annual_vol_strategy: float
    annual_vol_benchmark: float
    max_drawdown_strategy: float    # negative, e.g. -0.21
    max_drawdown_benchmark: float   # negative, e.g. -0.33
    sharpe_strategy: float
    sharpe_benchmark: float

    def __str__(self) -> str:
        return (
            f"{'':22} {'满仓':>10} {'动态仓位':>10}\n"
            f"{'年化收益':22} {self.annual_return_benchmark:>+10.1%}"
            f" {self.annual_return_strategy:>+10.1%}\n"
            f"{'年化波动率':22} {self.annual_vol_benchmark:>10.1%}"
            f" {self.annual_vol_strategy:>10.1%}\n"
            f"{'最大回撤':22} {self.max_drawdown_benchmark:>10.1%}"
            f" {self.max_drawdown_strategy:>10.1%}\n"
            f"{'夏普比率':22} {self.sharpe_benchmark:>10.2f}"
            f" {self.sharpe_strategy:>10.2f}"
        )


class PositionSizingBacktest:
    """
    Weekly-rebalanced volatility targeting backtest.

    Every Friday: recompute position from trailing 20-day vol.
    Strategy weekly return = position × index weekly return.
    Benchmark: 100% invested throughout.
    """

    def __init__(self, target_vol: float = 0.20, risk_free: float = 0.03) -> None:
        self._target_vol = target_vol
        self._risk_free = risk_free
        self._calc = VolatilityCalculator()

    def run(self, prices: pd.Series) -> BacktestResult:
        """Run the backtest on a daily price series."""
        weekly = prices.resample("W-FRI").last().dropna()
        daily_vol = self._calc.rolling_vol(prices)

        strategy_rets, benchmark_rets = [], []

        for i in range(1, len(weekly)):
            prev_date = weekly.index[i - 1]
            vol_series = daily_vol.loc[:prev_date].dropna()
            if len(vol_series) < 1:
                continue
            vol = float(vol_series.iloc[-1])
            position = min(1.0, self._target_vol / vol) if vol > 0 else 1.0

            weekly_ret = float(weekly.iloc[i] / weekly.iloc[i - 1] - 1)
            strategy_rets.append(position * weekly_ret)
            benchmark_rets.append(weekly_ret)

        n = len(strategy_rets)
        if n == 0:
            raise ValueError("No weekly returns computed — price series too short to run backtest")

        s = np.array(strategy_rets)
        b = np.array(benchmark_rets)

        ann_ret_s = float((1 + s).prod() ** (WEEKS_PER_YEAR / n) - 1)
        ann_ret_b = float((1 + b).prod() ** (WEEKS_PER_YEAR / n) - 1)
        ann_vol_s = float(s.std(ddof=1) * math.sqrt(WEEKS_PER_YEAR))
        ann_vol_b = float(b.std(ddof=1) * math.sqrt(WEEKS_PER_YEAR))

        rf_weekly = (1 + self._risk_free) ** (1 / WEEKS_PER_YEAR) - 1
        sharpe_s = float((s - rf_weekly).mean() / s.std(ddof=1) * math.sqrt(WEEKS_PER_YEAR)) if s.std(ddof=1) > 0 else 0.0
        sharpe_b = float((b - rf_weekly).mean() / b.std(ddof=1) * math.sqrt(WEEKS_PER_YEAR)) if b.std(ddof=1) > 0 else 0.0

        return BacktestResult(
            annual_return_strategy=round(ann_ret_s, 4),
            annual_return_benchmark=round(ann_ret_b, 4),
            annual_vol_strategy=round(ann_vol_s, 4),
            annual_vol_benchmark=round(ann_vol_b, 4),
            max_drawdown_strategy=round(self._max_drawdown(s), 4),
            max_drawdown_benchmark=round(self._max_drawdown(b), 4),
            sharpe_strategy=round(sharpe_s, 3),
            sharpe_benchmark=round(sharpe_b, 3),
        )

    @staticmethod
    def _max_drawdown(returns: np.ndarray) -> float:
        cumulative = np.cumprod(1 + returns)
        rolling_max = np.maximum.accumulate(cumulative)
        return float((cumulative / rolling_max - 1).min())

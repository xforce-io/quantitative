"""Backtest low-frequency allocation signals against buy-and-hold."""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd


PERIODS_PER_YEAR = 12


@dataclass(frozen=True)
class LowFrequencyBacktestResult:
    """Summary and equity curves for a low-frequency backtest."""

    metrics: dict
    equity_curve: pd.DataFrame
    monthly_returns: pd.DataFrame


class LowFrequencyBacktester:
    """Backtest target-position signals on month-end close returns."""

    REQUIRED_SIGNAL_COLUMNS = ("close", "target_position")

    def __init__(self, risk_free: float = 0.03, transaction_cost: float = 0.0) -> None:
        self.risk_free = risk_free
        self.transaction_cost = transaction_cost
        if transaction_cost < 0:
            raise ValueError("transaction_cost must be non-negative")

    def run(self, signals: pd.DataFrame) -> LowFrequencyBacktestResult:
        """Run a monthly low-frequency allocation backtest."""
        data = self._prepare_signals(signals)
        monthly_return = data["close"].pct_change().fillna(0.0)
        position = data["target_position"].shift(1).fillna(0.0)
        turnover = data["target_position"].diff().abs().fillna(data["target_position"].abs())

        strategy_return = position * monthly_return - turnover * self.transaction_cost
        benchmark_return = monthly_return

        equity_curve = pd.DataFrame(
            {
                "strategy": (1.0 + strategy_return).cumprod(),
                "benchmark": (1.0 + benchmark_return).cumprod(),
                "target_position": data["target_position"],
            },
            index=data.index,
        )
        monthly_returns = pd.DataFrame(
            {
                "strategy": strategy_return,
                "benchmark": benchmark_return,
                "position": position,
                "turnover": turnover,
            },
            index=data.index,
        )
        metrics = self._metrics(strategy_return, benchmark_return, equity_curve)
        return LowFrequencyBacktestResult(metrics, equity_curve, monthly_returns)

    def _prepare_signals(self, signals: pd.DataFrame) -> pd.DataFrame:
        """Validate and normalize signal input."""
        if signals is None or signals.empty:
            raise ValueError("signals must be a non-empty DataFrame")

        missing = [col for col in self.REQUIRED_SIGNAL_COLUMNS if col not in signals.columns]
        if missing:
            raise ValueError(f"signals missing required columns: {', '.join(missing)}")

        data = signals.copy()
        if not isinstance(data.index, pd.DatetimeIndex):
            data.index = pd.to_datetime(data.index)
        data = data.sort_index()
        data["close"] = pd.to_numeric(data["close"], errors="coerce")
        data["target_position"] = pd.to_numeric(data["target_position"], errors="coerce")
        data = data.dropna(subset=["close", "target_position"])
        data["target_position"] = data["target_position"].clip(0.0, 1.0)

        if len(data) < 2:
            raise ValueError("signals must contain at least two rebalance rows")
        return data

    def _metrics(
        self,
        strategy_return: pd.Series,
        benchmark_return: pd.Series,
        equity_curve: pd.DataFrame,
    ) -> dict:
        """Compute standard monthly backtest metrics."""
        return {
            "total_return_strategy": self._total_return(equity_curve["strategy"]),
            "total_return_benchmark": self._total_return(equity_curve["benchmark"]),
            "annual_return_strategy": self._annual_return(strategy_return),
            "annual_return_benchmark": self._annual_return(benchmark_return),
            "annual_vol_strategy": self._annual_vol(strategy_return),
            "annual_vol_benchmark": self._annual_vol(benchmark_return),
            "max_drawdown_strategy": self._max_drawdown(equity_curve["strategy"]),
            "max_drawdown_benchmark": self._max_drawdown(equity_curve["benchmark"]),
            "sharpe_strategy": self._sharpe(strategy_return),
            "sharpe_benchmark": self._sharpe(benchmark_return),
        }

    @staticmethod
    def _total_return(equity: pd.Series) -> float:
        return round(float(equity.iloc[-1] / equity.iloc[0] - 1.0), 4)

    @staticmethod
    def _annual_return(returns: pd.Series) -> float:
        n = len(returns)
        if n == 0:
            return 0.0
        total = float((1.0 + returns).prod())
        return round(total ** (PERIODS_PER_YEAR / n) - 1.0, 4)

    @staticmethod
    def _annual_vol(returns: pd.Series) -> float:
        if len(returns) < 2:
            return 0.0
        return round(float(returns.std(ddof=1) * math.sqrt(PERIODS_PER_YEAR)), 4)

    @staticmethod
    def _max_drawdown(equity: pd.Series) -> float:
        drawdown = equity / equity.cummax() - 1.0
        return round(float(drawdown.min()), 4)

    def _sharpe(self, returns: pd.Series) -> float:
        if len(returns) < 2:
            return 0.0
        vol = returns.std(ddof=1)
        if vol == 0 or np.isnan(vol):
            return 0.0
        rf_monthly = (1.0 + self.risk_free) ** (1.0 / PERIODS_PER_YEAR) - 1.0
        return round(float((returns - rf_monthly).mean() / vol * math.sqrt(PERIODS_PER_YEAR)), 3)
